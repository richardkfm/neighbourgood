"""Review and rating endpoints for completed bookings and skill endorsements."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.booking import Booking
from app.models.community import CommunityMember
from app.models.resource import Resource
from app.models.review import Review
from app.models.skill import Skill
from app.models.user import User
from app.schemas.review import ReviewCreate, ReviewOut, ReviewSummary, SkillReviewCreate

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def create_review(
    body: ReviewCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Leave a review for a completed booking (borrower reviews lender, or vice versa)."""
    booking = (
        db.query(Booking)
        .options(joinedload(Booking.resource))
        .filter(Booking.id == body.booking_id)
        .first()
    )
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    if booking.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Can only review completed bookings",
        )

    resource = booking.resource
    is_borrower = booking.borrower_id == current_user.id
    is_lender = resource.owner_id == current_user.id if resource else False

    if not is_borrower and not is_lender:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the borrower or lender can review this booking",
        )

    # Determine who is being reviewed
    if is_borrower:
        reviewee_id = resource.owner_id if resource else booking.borrower_id
    else:
        reviewee_id = booking.borrower_id

    # Check for duplicate review
    existing = (
        db.query(Review)
        .filter(
            Review.booking_id == body.booking_id,
            Review.reviewer_id == current_user.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already reviewed this booking",
        )

    review = Review(
        booking_id=body.booking_id,
        review_type="booking",
        reviewer_id=current_user.id,
        reviewee_id=reviewee_id,
        rating=body.rating,
        comment=body.comment,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    _ = review.reviewer
    _ = review.reviewee
    return review


@router.post("/skill", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def create_skill_review(
    body: SkillReviewCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Leave an endorsement/review for a skill listing. Must share a community with the skill owner."""
    skill = db.query(Skill).filter(Skill.id == body.skill_id).first()
    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")

    if skill.owner_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot review your own skill",
        )

    # Verify reviewer shares a community with the skill
    if skill.community_id:
        reviewer_in_community = (
            db.query(CommunityMember)
            .filter(
                CommunityMember.community_id == skill.community_id,
                CommunityMember.user_id == current_user.id,
            )
            .first()
        )
        if not reviewer_in_community:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must be a member of the skill's community to review it",
            )

    # Duplicate check
    existing = (
        db.query(Review)
        .filter(
            Review.skill_id == body.skill_id,
            Review.reviewer_id == current_user.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already reviewed this skill",
        )

    review = Review(
        skill_id=body.skill_id,
        review_type="skill",
        reviewer_id=current_user.id,
        reviewee_id=skill.owner_id,
        rating=body.rating,
        comment=body.comment,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    _ = review.reviewer
    _ = review.reviewee
    return review


@router.get("/booking/{booking_id}", response_model=list[ReviewOut])
def get_booking_reviews(booking_id: int, db: Session = Depends(get_db)):
    """Get all reviews for a specific booking."""
    reviews = (
        db.query(Review)
        .options(joinedload(Review.reviewer), joinedload(Review.reviewee))
        .filter(Review.booking_id == booking_id)
        .order_by(Review.created_at.desc())
        .all()
    )
    return reviews


@router.get("/skill/{skill_id}", response_model=list[ReviewOut])
def get_skill_reviews(
    skill_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get all reviews/endorsements for a skill listing."""
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")

    reviews = (
        db.query(Review)
        .options(joinedload(Review.reviewer), joinedload(Review.reviewee))
        .filter(Review.skill_id == skill_id, Review.review_type == "skill")
        .order_by(Review.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return reviews


@router.get("/user/{user_id}", response_model=list[ReviewOut])
def get_user_reviews(
    user_id: int,
    review_type: str | None = Query(None, description="Filter: booking, skill, or given"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get reviews for a user. By default returns received reviews. Use type=given for given reviews."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    query = db.query(Review).options(
        joinedload(Review.reviewer), joinedload(Review.reviewee)
    )

    if review_type == "given":
        query = query.filter(Review.reviewer_id == user_id)
    elif review_type == "booking":
        query = query.filter(Review.reviewee_id == user_id, Review.review_type == "booking")
    elif review_type == "skill":
        query = query.filter(Review.reviewee_id == user_id, Review.review_type == "skill")
    else:
        query = query.filter(Review.reviewee_id == user_id)

    reviews = (
        query.order_by(Review.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return reviews


@router.get("/user/{user_id}/summary", response_model=ReviewSummary)
def get_user_review_summary(user_id: int, db: Session = Depends(get_db)):
    """Get average rating and total review count for a user, broken down by type."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Overall
    result = (
        db.query(
            sqlfunc.count(Review.id).label("total"),
            sqlfunc.avg(Review.rating).label("avg"),
        )
        .filter(Review.reviewee_id == user_id)
        .first()
    )
    total = result.total or 0
    avg = round(float(result.avg), 2) if result.avg else 0.0

    # Breakdown: booking reviews where user was lender (borrower reviewed them)
    lender_result = (
        db.query(
            sqlfunc.count(Review.id).label("total"),
            sqlfunc.avg(Review.rating).label("avg"),
        )
        .join(Booking, Booking.id == Review.booking_id)
        .join(Resource, Resource.id == Booking.resource_id)
        .filter(
            Review.reviewee_id == user_id,
            Review.review_type == "booking",
            Resource.owner_id == user_id,
        )
        .first()
    )

    # Breakdown: booking reviews where user was borrower (lender reviewed them)
    borrower_result = (
        db.query(
            sqlfunc.count(Review.id).label("total"),
            sqlfunc.avg(Review.rating).label("avg"),
        )
        .join(Booking, Booking.id == Review.booking_id)
        .filter(
            Review.reviewee_id == user_id,
            Review.review_type == "booking",
            Booking.borrower_id == user_id,
        )
        .first()
    )

    # Breakdown: skill reviews
    skill_result = (
        db.query(
            sqlfunc.count(Review.id).label("total"),
            sqlfunc.avg(Review.rating).label("avg"),
        )
        .filter(Review.reviewee_id == user_id, Review.review_type == "skill")
        .first()
    )

    return ReviewSummary(
        user_id=user_id,
        average_rating=avg,
        total_reviews=total,
        lender_avg=round(float(lender_result.avg), 2) if lender_result.avg else 0.0,
        lender_count=lender_result.total or 0,
        borrower_avg=round(float(borrower_result.avg), 2) if borrower_result.avg else 0.0,
        borrower_count=borrower_result.total or 0,
        skill_avg=round(float(skill_result.avg), 2) if skill_result.avg else 0.0,
        skill_count=skill_result.total or 0,
    )
