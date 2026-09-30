"""Crisis mode changes and the 60% member vote.

Shared by the REST crisis endpoints, mesh sync and membership changes so
every path that changes a community's stored mode clears stale votes, and
every change in membership re-evaluates the threshold.
"""

from sqlalchemy.orm import Session

from app.models.community import Community, CommunityMember
from app.models.crisis import CrisisVote
from app.services.activity import record_activity

VOTE_THRESHOLD_PCT = 60  # percentage of members needed to trigger mode change


def pending_vote_type(stored_mode: str) -> str:
    """The only vote that can change a community in ``stored_mode``."""
    return "deactivate" if stored_mode == "red" else "activate"


def is_noop_vote(stored_mode: str, vote_type: str) -> bool:
    """"activate" while red or "deactivate" while blue changes nothing."""
    return vote_type != pending_vote_type(stored_mode)


def set_community_mode(db: Session, community: Community, mode: str) -> bool:
    """Set the stored mode and clear all votes. Returns True if the mode changed.

    Votes are cleared even when the mode is unchanged (an admin override resets
    the vote). Only flushes: the caller owns the transaction.
    """
    changed = community.mode != mode
    community.mode = mode
    db.query(CrisisVote).filter(CrisisVote.community_id == community.id).delete(
        synchronize_session=False
    )
    db.flush()
    return changed


def threshold_needed(total_members: int) -> int:
    return max(1, (total_members * VOTE_THRESHOLD_PCT + 99) // 100)


def apply_vote_threshold(
    db: Session,
    community_id: int,
    vote_type: str,
    actor_id: int,
    *,
    commit: bool = True,
) -> str | None:
    """Switch the community mode if ``vote_type`` has reached the threshold.

    Returns the new mode ("red"/"blue") when a switch happened, else None.
    With ``commit=False`` the caller owns the transaction (changes are only flushed).
    """
    total_members = (
        db.query(CommunityMember)
        .filter(CommunityMember.community_id == community_id)
        .count()
    )
    vote_count = (
        db.query(CrisisVote)
        .filter(
            CrisisVote.community_id == community_id,
            CrisisVote.vote_type == vote_type,
        )
        .count()
    )
    if total_members == 0 or vote_count < threshold_needed(total_members):
        return None

    new_mode = "red" if vote_type == "activate" else "blue"
    # Re-fetch the community row with a row-level lock (no-op on SQLite, but
    # PostgreSQL serialises concurrent voters here) and re-check the mode
    # under the lock, so two voters crossing the threshold flip it only once.
    locked_community = (
        db.query(Community)
        .filter(Community.id == community_id)
        .with_for_update()
        .first()
    )
    if locked_community is None or locked_community.mode == new_mode:
        return None

    set_community_mode(db, locked_community, new_mode)
    if commit:
        db.commit()

    label = "Red Sky (crisis)" if new_mode == "red" else "Blue Sky (normal)"
    record_activity(
        db,
        event_type="crisis_mode_changed",
        summary=f'community vote switched "{locked_community.name}" to {label}',
        actor_id=actor_id,
        community_id=community_id,
        commit=commit,
    )
    return new_mode


def handle_member_removed(
    db: Session, community_id: int, user_id: int, *, commit: bool = True
) -> str | None:
    """Drop a departed member's vote and re-check the threshold with the smaller membership.

    Call after the membership row is deleted (leave, removal, account deletion).
    Returns the new mode if the remaining votes now reach the threshold.
    """
    db.query(CrisisVote).filter(
        CrisisVote.community_id == community_id, CrisisVote.user_id == user_id
    ).delete(synchronize_session=False)
    db.flush()
    community = db.query(Community).filter(Community.id == community_id).first()
    if community is None:
        if commit:
            db.commit()
        return None
    new_mode = apply_vote_threshold(
        db, community_id, pending_vote_type(community.mode), user_id, commit=commit
    )
    if new_mode is None and commit:
        db.commit()
    return new_mode
