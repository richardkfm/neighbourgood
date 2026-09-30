"""Account deletion: anonymise the user and clean up everything that only they owned.

The ``users`` row is kept (anonymised) so messages, reviews, emergency tickets and
other people's booking history keep pointing at a valid row and simply show
"Deleted user". Everything else is either deleted, detached or left alone as
documented per table below; nothing is left referencing a row that no longer exists.

=============================  ==========================================================
Table / column                 Treatment
=============================  ==========================================================
resources.owner_id             Deleted. A resource that other people have booking history
                               on (bookings, and through them reviews) cannot be deleted
                               without destroying their records, so it is scrubbed into an
                               unavailable "Deleted listing" tombstone outside any community.
skills.owner_id                Deleted; messages/reviews that mention the skill are
                               detached (skill_id -> NULL) and kept.
bookings.borrower_id           Pending/approved bookings cancelled; history kept.
community_members.user_id      Deleted (see promotion / deactivation rules below).
crisis_votes.user_id           Deleted (a vote belongs to a membership that no longer exists).
emergency_tickets.author_id    Kept. ticket_comments.author_id kept.
emergency_tickets.assigned_to  Cleared; an in-progress ticket goes back to "open".
events.organizer_id            Upcoming events deleted (with their RSVPs); past events kept.
event_attendees.user_id        Deleted.
invites.created_by_id          Deleted (an invite from a deleted person should stop working).
activities.actor_id            Deleted, except crisis/ticket/leader entries (kept).
mesh_checkins.user_id          Deleted (location data).
mesh_synced_messages           Kept (de-duplication log needed by the mesh sync).
sent_red_sky_alerts.sent_by_id Kept (other instances verify alerts against it).
communities.created_by_id      Kept.
messages / reviews             Kept.
webhooks / telegram_link_tokens / password_reset_tokens   Deleted.
=============================  ==========================================================
"""

import datetime
import os
import secrets
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.activity import Activity
from app.models.booking import Booking
from app.models.community import Community, CommunityMember
from app.models.crisis import CrisisVote, EmergencyTicket
from app.models.event import Event, EventAttendee
from app.models.invite import Invite
from app.models.mesh import MeshDeviceKey
from app.models.mesh_checkin import MeshCheckin
from app.models.message import Message
from app.models.password_reset import PasswordResetToken
from app.models.resource import Resource
from app.models.review import Review
from app.models.skill import Skill
from app.models.user import User
from app.models.webhook import TelegramLinkToken, Webhook
from app.services.auth import hash_password
from app.services.crisis_votes import handle_member_removed

DELETED_DISPLAY_NAME = "Deleted user"
DELETED_LISTING_TITLE = "Deleted listing"
_KEPT_ACTIVITY_TYPES = ("crisis_mode_changed", "ticket_created", "leader_promoted", "leader_demoted")


@dataclass
class DeletionResult:
    """What the caller still has to do after the commit (send notifications, remove files)."""

    # (borrower email, resource title) for bookings cancelled because the owner left
    cancelled_borrowers: list[tuple[str, str]] = field(default_factory=list)
    image_paths: list[str] = field(default_factory=list)


def _cancel_active_bookings(db: Session, resource_id: int) -> list[Booking]:
    bookings = (
        db.query(Booking)
        .filter(Booking.resource_id == resource_id, Booking.status.in_(["pending", "approved"]))
        .all()
    )
    for booking in bookings:
        booking.status = "cancelled"
    return bookings


def _delete_resources(db: Session, user: User, result: DeletionResult) -> None:
    for resource in db.query(Resource).filter(Resource.owner_id == user.id).all():
        for booking in _cancel_active_bookings(db, resource.id):
            borrower = db.query(User).filter(User.id == booking.borrower_id).first()
            if borrower and borrower.is_active:
                result.cancelled_borrowers.append((borrower.email, resource.title))

        if resource.image_path:
            result.image_paths.append(resource.image_path)

        has_history = db.query(Booking.id).filter(Booking.resource_id == resource.id).first()
        if has_history:
            # Other people's booking (and review) history points here: keep the row as a tombstone.
            resource.title = DELETED_LISTING_TITLE
            resource.description = None
            resource.image_path = None
            resource.is_available = False
            resource.quantity_available = 0
            resource.community_id = None
        else:
            db.delete(resource)


def _delete_skills(db: Session, user: User) -> None:
    for skill in db.query(Skill).filter(Skill.owner_id == user.id).all():
        # Messages and endorsements outlive the listing; detach them so the foreign
        # keys (enforced on PostgreSQL) do not block the delete.
        db.query(Message).filter(Message.skill_id == skill.id).update(
            {Message.skill_id: None}, synchronize_session=False
        )
        db.query(Review).filter(Review.skill_id == skill.id).update(
            {Review.skill_id: None}, synchronize_session=False
        )
        db.delete(skill)


def _leave_communities(db: Session, user: User) -> None:
    memberships = db.query(CommunityMember).filter(CommunityMember.user_id == user.id).all()
    for membership in memberships:
        community_id = membership.community_id
        was_admin = membership.role == "admin"
        db.delete(membership)
        db.flush()

        community = db.query(Community).filter(Community.id == community_id).first()
        if community is None or not community.is_active or community.merged_into_id is not None:
            continue  # stale row left behind by a merge; nothing to hand over

        remaining = (
            db.query(CommunityMember)
            .filter(CommunityMember.community_id == community_id)
            .order_by(CommunityMember.joined_at, CommunityMember.id)
            .all()
        )
        if not remaining:
            community.is_active = False
            continue
        if was_admin and not any(m.role == "admin" for m in remaining):
            remaining[0].role = "admin"  # longest-standing member takes over
        # The smaller membership may now reach the crisis-vote threshold
        handle_member_removed(db, community_id, user.id, commit=False)


def _delete_events(db: Session, user: User) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    upcoming = db.query(Event).filter(Event.organizer_id == user.id, Event.start_at > now).all()
    for event in upcoming:
        db.delete(event)  # RSVPs go with it (ORM cascade)
    db.flush()
    db.query(EventAttendee).filter(EventAttendee.user_id == user.id).delete(
        synchronize_session=False
    )


def _cancel_own_bookings(db: Session, user: User) -> None:
    db.query(Booking).filter(
        Booking.borrower_id == user.id, Booking.status.in_(["pending", "approved"])
    ).update({Booking.status: "cancelled"}, synchronize_session=False)


def _release_tickets(db: Session, user: User) -> None:
    tickets = db.query(EmergencyTicket).filter(EmergencyTicket.assigned_to_id == user.id).all()
    for ticket in tickets:
        ticket.assigned_to_id = None
        if ticket.status == "in_progress":
            ticket.status = "open"


def _anonymise(user: User) -> None:
    user.display_name = DELETED_DISPLAY_NAME
    user.email = f"deleted-{user.id}@invalid"
    # A valid hash of a secret nobody ever sees: the account can no longer be logged into.
    user.hashed_password = hash_password(secrets.token_urlsafe(32))
    user.neighbourhood = None
    user.telegram_chat_id = None
    user.language_code = "en"
    user.mesh_public_key = None
    user.role = "member"
    user.is_active = False


def delete_account(db: Session, user: User) -> DeletionResult:
    """Delete *user*'s account in one transaction (commits on success)."""
    result = DeletionResult()

    _delete_resources(db, user, result)
    _delete_skills(db, user)
    _cancel_own_bookings(db, user)
    _leave_communities(db, user)
    _delete_events(db, user)
    _release_tickets(db, user)

    db.query(CrisisVote).filter(CrisisVote.user_id == user.id).delete(synchronize_session=False)
    db.query(Invite).filter(Invite.created_by_id == user.id).delete(synchronize_session=False)
    # Crisis feed entries stay with the tickets they describe; personal sharing activity goes.
    db.query(Activity).filter(
        Activity.actor_id == user.id, Activity.event_type.notin_(_KEPT_ACTIVITY_TYPES)
    ).delete(synchronize_session=False)
    db.query(MeshCheckin).filter(MeshCheckin.user_id == user.id).delete(synchronize_session=False)
    # Revoked (not deleted) so signatures made with these keys stop verifying
    db.query(MeshDeviceKey).filter(
        MeshDeviceKey.user_id == user.id, MeshDeviceKey.revoked_at.is_(None)
    ).update({MeshDeviceKey.revoked_at: datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)},
             synchronize_session=False)
    db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user.id).delete(
        synchronize_session=False
    )
    db.query(Webhook).filter(Webhook.owner_type == "user", Webhook.owner_id == user.id).delete(
        synchronize_session=False
    )
    db.query(TelegramLinkToken).filter(
        TelegramLinkToken.token_type == "user", TelegramLinkToken.owner_id == user.id
    ).delete(synchronize_session=False)

    _anonymise(user)
    db.commit()
    return result


def remove_image_files(paths: list[str]) -> None:
    for path in paths:
        try:
            os.remove(path)
        except OSError:
            pass
