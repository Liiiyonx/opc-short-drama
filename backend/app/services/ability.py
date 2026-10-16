"""能力图谱服务：个人五维能力与成长曲线 / 班级分布（W6）。"""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import StudentProfile
from app.models.review import ABILITY_DIMENSIONS, AbilitySnapshot
from app.models.user import User


def _forbidden(message: str = "无权查看该数据") -> HTTPException:
    return HTTPException(status_code=403, detail={"code": 40301, "message": message})


async def get_student_ability(
    db: AsyncSession, user: User, student_id: int
) -> dict:
    if user.role not in ("teacher", "admin") and user.id != student_id:
        raise _forbidden()

    rows = (
        (
            await db.execute(
                select(AbilitySnapshot)
                .where(AbilitySnapshot.student_id == student_id)
                .order_by(AbilitySnapshot.id.desc())
                .limit(200)
            )
        )
        .scalars()
        .all()
    )

    latest: dict[str, float] = {}
    history = []
    ref_ids = set()
    for row in rows:
        score = float(row.score)
        history.append(
            {
                "dimension": row.dimension,
                "score": score,
                "source": row.source,
                "created_at": row.created_at,
            }
        )
        if row.dimension not in latest:
            latest[row.dimension] = score
        if row.ref_id:
            ref_ids.add(row.ref_id)

    return {
        "student_id": student_id,
        "latest": latest,
        "history": history,
        "review_count": len(ref_ids),
    }


async def get_class_ability(db: AsyncSession, user: User, class_id: int) -> dict:
    if user.role not in ("teacher", "admin"):
        raise _forbidden()
    profiles = (
        (
            await db.execute(
                select(StudentProfile).where(StudentProfile.class_id == class_id)
            )
        )
        .scalars()
        .all()
    )
    student_ids = [profile.user_id for profile in profiles]
    averages: dict[str, float] = {}
    if student_ids:
        for dimension in ABILITY_DIMENSIONS:
            scores = []
            for student_id in student_ids:
                row = (
                    await db.execute(
                        select(AbilitySnapshot)
                        .where(
                            AbilitySnapshot.student_id == student_id,
                            AbilitySnapshot.dimension == dimension,
                        )
                        .order_by(AbilitySnapshot.id.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if row is not None:
                    scores.append(float(row.score))
            if scores:
                averages[dimension] = round(sum(scores) / len(scores), 2)
    return {
        "class_id": class_id,
        "student_count": len(student_ids),
        "averages": averages,
    }
