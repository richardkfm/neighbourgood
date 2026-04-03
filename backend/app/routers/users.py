"""User profile, reputation, and trust endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.booking import Booking
from app.models.message import Message
from app.models.resource import Resource
from app.models.review import Review
from app.models.skill import Skill
from app.models.user import User
from app.schemas.user import (
    ChangeEmail,
    ChangePassword,
    DashboardOverview,
    OwnerTrust,
    ReputationOut,
    TrustBadge,
    TrustSummary,
    UserProfile,
    UserProfileUpdate,
)
from app.services.auth import hash_password, verify_password

router = APIRouter(prefix="/users", tags=["users"])

# ── Reputation scoring weights ─────────────────────────────────────

POINTS_RESOURCE_SHARED = 2
POINTS_BOOKING_COMPLETED_LENDER = 10
POINTS_BOOKING_COMPLETED_BORROWER = 5
POINTS_SKILL_OFFERED = 2
POINTS_SKILL_REQUESTED = 1

REPUTATION_LEVELS = [
    (0, "Newcomer"),
    (10, "Neighbour"),
    (40, "Helper"),
    (100, "Trusted"),
    (200, "Pillar"),
]


def _compute_reputation(db: Session, user_id: int) -> dict:
    """Compute reputation score and breakdown for a user."""
    resources_shared = db.query(Resource).filter(Resource.owner_id == user_id).count()

    bookings_completed_lender = (
        db.query(Booking)
        .join(Resource, Resource.id == Booking.resource_id)
        .filter(Resource.owner_id == user_id, Booking.status == "completed")
        .count()
    )

    bookings_completed_borrower = (
        db.query(Booking)
        .filter(Booking.borrower_id == user_id, Booking.status == "completed")
        .count()
    )

    skills_offered = (
        db.query(Skill).filter(Skill.owner_id == user_id, Skill.skill_type == "offer").count()
    )
    skills_requested = (
        db.query(Skill).filter(Skill.owner_id == user_id, Skill.skill_type == "request").count()
    )

    breakdown = {
        "resources_shared": resources_shared * POINTS_RESOURCE_SHARED,
        "lending_completed": bookings_completed_lender * POINTS_BOOKING_COMPLETED_LENDER,
        "borrowing_completed": bookings_completed_borrower * POINTS_BOOKING_COMPLETED_BORROWER,
        "skills_offered": skills_offered * POINTS_SKILL_OFFERED,
        "skills_requested": skills_requested * POINTS_SKILL_REQUESTED,
    }

    score = sum(breakdown.values())

    level = "Newcomer"
    for threshold, label in REPUTATION_LEVELS:
        if score >= threshold:
            level = label

    return {"score": score, "level": level, "breakdown": breakdown}


# Badge threshold: avg >= 4.0 AND count >= 3
_BADGE_MIN_COUNT = 3
_BADGE_MIN_AVG = 4.0

_BADGE_DEFS = {
    "reliable_borrower": {"label": "Reliable Borrower", "desc_tpl": "{avg:.1f} avg from {count} borrowing reviews"},
    "trusted_lender": {"label": "Trusted Lender", "desc_tpl": "{avg:.1f} avg from {count} lending reviews"},
    "skilled_helper": {"label": "Skilled Helper", "desc_tpl": "{avg:.1f} avg from {count} skill reviews"},
}


def _compute_trust(db: Session, user: User) -> dict:
    """Compute trust summary with badges for a user."""
    rep = _compute_reputation(db, user.id)

    # Overall reviews received
    overall = (
        db.query(
            sqlfunc.count(Review.id).label("total"),
            sqlfunc.avg(Review.rating).label("avg"),
        )
        .filter(Review.reviewee_id == user.id)
        .first()
    )
    total_reviews = overall.total or 0
    average_rating = round(float(overall.avg), 2) if overall.avg else 0.0

    # Lender reviews: booking reviews where user was the resource owner
    lender = (
        db.query(
            sqlfunc.count(Review.id).label("total"),
            sqlfunc.avg(Review.rating).label("avg"),
        )
        .join(Booking, Booking.id == Review.booking_id)
        .join(Resource, Resource.id == Booking.resource_id)
        .filter(
            Review.reviewee_id == user.id,
            Review.review_type == "booking",
            Resource.owner_id == user.id,
        )
        .first()
    )

    # Borrower reviews: booking reviews where user was the borrower
    borrower = (
        db.query(
            sqlfunc.count(Review.id).label("total"),
            sqlfunc.avg(Review.rating).label("avg"),
        )
        .join(Booking, Booking.id == Review.booking_id)
        .filter(
            Review.reviewee_id == user.id,
            Review.review_type == "booking",
            Booking.borrower_id == user.id,
        )
        .first()
    )

    # Skill reviews
    skill = (
        db.query(
            sqlfunc.count(Review.id).label("total"),
            sqlfunc.avg(Review.rating).label("avg"),
        )
        .filter(Review.reviewee_id == user.id, Review.review_type == "skill")
        .first()
    )

    lender_count = lender.total or 0
    lender_avg = round(float(lender.avg), 2) if lender.avg else 0.0
    borrower_count = borrower.total or 0
    borrower_avg = round(float(borrower.avg), 2) if borrower.avg else 0.0
    skill_count = skill.total or 0
    skill_avg = round(float(skill.avg), 2) if skill.avg else 0.0

    # Compute badges
    badges: list[TrustBadge] = []
    category_data = {
        "reliable_borrower": (borrower_avg, borrower_count),
        "trusted_lender": (lender_avg, lender_count),
        "skilled_helper": (skill_avg, skill_count),
    }
    for key, (avg, count) in category_data.items():
        if count >= _BADGE_MIN_COUNT and avg >= _BADGE_MIN_AVG:
            defn = _BADGE_DEFS[key]
            badges.append(TrustBadge(
                key=key,
                label=defn["label"],
                description=defn["desc_tpl"].format(avg=avg, count=count),
            ))

    resources_count = db.query(Resource).filter(Resource.owner_id == user.id).count()
    skills_count = db.query(Skill).filter(Skill.owner_id == user.id).count()

    return {
        "user_id": user.id,
        "display_name": user.display_name,
        "neighbourhood": user.neighbourhood,
        "member_since": user.created_at,
        "reputation_level": rep["level"],
        "reputation_score": rep["score"],
        "average_rating": average_rating,
        "total_reviews": total_reviews,
        "badges": badges,
        "lender_rating": lender_avg,
        "lender_reviews": lender_count,
        "borrower_rating": borrower_avg,
        "borrower_reviews": borrower_count,
        "skill_rating": skill_avg,
        "skill_reviews": skill_count,
        "resources_count": resources_count,
        "skills_count": skills_count,
    }


def compute_owner_trust(db: Session, user_id: int) -> OwnerTrust:
    """Compute a compact trust summary for embedding in listings."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return OwnerTrust(reputation_level="Newcomer", average_rating=0.0, total_reviews=0, badges=[])
    trust = _compute_trust(db, user)
    return OwnerTrust(
        reputation_level=trust["reputation_level"],
        average_rating=trust["average_rating"],
        total_reviews=trust["total_reviews"],
        badges=[b.key for b in trust["badges"]],
    )


@router.get("/me", response_model=UserProfile)
def get_my_profile(current_user: User = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return current_user


@router.patch("/me", response_model=UserProfile)
def update_my_profile(
    body: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the authenticated user's profile fields. Username changes are prohibited for security."""
    if body.display_name is not None:
        current_user.display_name = body.display_name
    if body.neighbourhood is not None:
        current_user.neighbourhood = body.neighbourhood
    if body.language_code is not None:
        current_user.language_code = body.language_code
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/me/reputation", response_model=ReputationOut)
def get_my_reputation(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the authenticated user's reputation score."""
    rep = _compute_reputation(db, current_user.id)
    return ReputationOut(
        user_id=current_user.id,
        display_name=current_user.display_name,
        **rep,
    )


@router.get("/{user_id}/reputation", response_model=ReputationOut)
def get_user_reputation(user_id: int, db: Session = Depends(get_db)):
    """Get a user's public reputation score."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    rep = _compute_reputation(db, user.id)
    return ReputationOut(
        user_id=user.id,
        display_name=user.display_name,
        **rep,
    )


@router.get("/me/dashboard", response_model=DashboardOverview)
def get_dashboard_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get dashboard overview with counts and reputation."""
    resources_count = db.query(Resource).filter(Resource.owner_id == current_user.id).count()

    skills_count = (
        db.query(Skill).filter(Skill.owner_id == current_user.id).count()
    )

    bookings_count = (
        db.query(Booking)
        .filter(
            ((Booking.borrower_id == current_user.id) | (Booking.resource_id.in_(
                db.query(Resource.id).filter(Resource.owner_id == current_user.id)
            )))
        )
        .count()
    )

    messages_unread_count = (
        db.query(Message)
        .filter(Message.recipient_id == current_user.id, Message.is_read == False)
        .count()
    )

    rep = _compute_reputation(db, current_user.id)

    return DashboardOverview(
        resources_count=resources_count,
        skills_count=skills_count,
        bookings_count=bookings_count,
        messages_unread_count=messages_unread_count,
        reputation_score=rep["score"],
        reputation_level=rep["level"],
    )


@router.post("/me/change-password", response_model=UserProfile)
def change_password(
    body: ChangePassword,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the authenticated user's password."""
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    current_user.hashed_password = hash_password(body.new_password)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/me/change-email", response_model=UserProfile)
def change_email(
    body: ChangeEmail,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the authenticated user's email."""
    if not verify_password(body.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password is incorrect",
        )

    existing_user = db.query(User).filter(User.email == body.new_email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Email already in use",
        )

    current_user.email = body.new_email
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/me/trust", response_model=TrustSummary)
def get_my_trust(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the authenticated user's trust summary with badges."""
    return TrustSummary(**_compute_trust(db, current_user))


@router.get("/{user_id}/trust", response_model=TrustSummary)
def get_user_trust(user_id: int, db: Session = Depends(get_db)):
    """Get a user's public trust summary with badges."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return TrustSummary(**_compute_trust(db, user))
