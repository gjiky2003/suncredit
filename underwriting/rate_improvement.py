"""On-time payment rate-improvement engine.

Drops APR 0.5% per 6 consecutive on-time payments, capped at 6 drops / 3% total.
"""


class RateImprovementEngine:
    """Reads loan payment history from db_conn and applies rate reductions."""

    DROP_PER_MILESTONE = 0.005   # 0.5% per 6 on-time payments
    PAYMENTS_PER_MILESTONE = 6
    MAX_DROPS = 6                # 6 * 0.5% = 3% max total reduction
    MAX_REDUCTION = 0.03

    def _fetch_loan(self, loan_id, db_conn):
        cur = db_conn.cursor()
        cur.execute(
            "SELECT id, original_apr, current_apr, on_time_streak FROM loans WHERE id = ?",
            (loan_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {"id": row[0], "original_apr": row[1], "current_apr": row[2], "on_time_streak": row[3] or 0}

    def apply_rate_improvement(self, loan_id, db_conn):
        loan = self._fetch_loan(loan_id, db_conn)
        if not loan:
            return {"error": "loan_not_found", "loan_id": loan_id}

        streak = int(loan["on_time_streak"] or 0)
        original_apr = float(loan["original_apr"])
        current_apr = float(loan["current_apr"])

        eligible_drops = min(streak // self.PAYMENTS_PER_MILESTONE, self.MAX_DROPS)
        target_reduction = min(eligible_drops * self.DROP_PER_MILESTONE, self.MAX_REDUCTION)
        target_apr = max(original_apr - target_reduction, original_apr - self.MAX_REDUCTION)

        applied = False
        if target_apr < current_apr - 1e-9:
            cur = db_conn.cursor()
            cur.execute("UPDATE loans SET current_apr = ? WHERE id = ?", (target_apr, loan_id))
            db_conn.commit()
            applied = True
            current_apr = target_apr

        return {
            "loan_id": loan_id,
            "original_apr": round(original_apr, 4),
            "current_apr": round(current_apr, 4),
            "reduction": round(original_apr - current_apr, 4),
            "streak": streak,
            "drops_applied": eligible_drops,
            "applied_now": applied,
        }

    def get_loan_status(self, loan_id, db_conn):
        loan = self._fetch_loan(loan_id, db_conn)
        if not loan:
            return {"error": "loan_not_found", "loan_id": loan_id}

        streak = int(loan["on_time_streak"] or 0)
        original_apr = float(loan["original_apr"])
        current_apr = float(loan["current_apr"])
        reduction = original_apr - current_apr
        drops_used = round(reduction / self.DROP_PER_MILESTONE)
        next_milestone_at = (drops_used + 1) * self.PAYMENTS_PER_MILESTONE
        if drops_used >= self.MAX_DROPS:
            next_milestone = None
        else:
            next_milestone = max(0, next_milestone_at - streak)

        return {
            "loan_id": loan_id,
            "original_apr": round(original_apr, 4),
            "current_apr": round(current_apr, 4),
            "reduction": round(reduction, 4),
            "streak": streak,
            "next_milestone": next_milestone,  # payments remaining; None if maxed
            "max_reduction_reached": drops_used >= self.MAX_DROPS,
        }
