"""能力图谱服务：个人五维能力与成长曲线 / 班级分布（W6）。

批量查询助手（latest_scores_by_*）供本模块与 tasks/orders 服务共用，
避免「每维度一次查询」「每人×每维一次查询」的 N+1 模式。
"""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import StudentProfile
from app.models.review import ABILITY_DIMENSIONS, AbilitySnapshot
from app.models.user import User


def _forbidden(message: str = "无权查看该数据") -> HTTPException:
    return HTTPException(status_code=403, detail={"code": 40301, "message": message})


async def latest_scores_by_dimension(
    db: AsyncSession, student_id: int
) -> dict[str, float]:
    """单个学生的「每维最新分」：一条查询，Python 侧取每维最大 id 行。"""
    rows = (
        (
            await db.execute(
                select(AbilitySnapshot)
                .where(
                    AbilitySnapshot.student_id == student_id,
                    AbilitySnapshot.dimension.in_(ABILITY_DIMENSIONS),
                )
                .order_by(AbilitySnapshot.id)
            )
        )
        .scalars()
        .all()
    )
    latest: dict[str, float] = {}
    for row in rows:  # id 升序 → 后者覆盖前者即最新
        latest[row.dimension] = float(row.score)
    return latest


async def latest_scores_by_students(
    db: AsyncSession, student_ids: list[int]
) -> dict[int, dict[str, float]]:
    """批量：{student_id: {dimension: 最新分}}，两条查询完成（无 N+1）。"""
    if not student_ids:
        return {}
    sub = (
        select(
            AbilitySnapshot.student_id.label("sid"),
            AbilitySnapshot.dimension.label("dim"),
            func.max(AbilitySnapshot.id).label("max_id"),
        )
        .where(AbilitySnapshot.student_id.in_(student_ids))
        .group_by(AbilitySnapshot.student_id, AbilitySnapshot.dimension)
        .subquery()
    )
    rows = (
        (
            await db.execute(
                select(AbilitySnapshot).join(
                    sub, AbilitySnapshot.id == sub.c.max_id
                )
            )
        )
        .scalars()
        .all()
    )
    result: dict[int, dict[str, float]] = {}
    for row in rows:
        result.setdefault(row.student_id, {})[row.dimension] = float(row.score)
    return result


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
        per_student = await latest_scores_by_students(db, student_ids)
        for dimension in ABILITY_DIMENSIONS:
            scores = [
                dims[dimension]
                for dims in per_student.values()
                if dimension in dims
            ]
            if scores:
                averages[dimension] = round(sum(scores) / len(scores), 2)
    return {
        "class_id": class_id,
        "student_count": len(student_ids),
        "averages": averages,
    }
