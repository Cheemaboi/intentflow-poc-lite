class RefundRepository:
    def mark_approved(self, refund_id: str) -> None:
        pass


def require_admin(actor) -> None:
    if actor.role != "ADMIN":
        raise PermissionError("Only ADMIN may approve refunds")


def approve_refund(actor, refund, repository: RefundRepository) -> None:
    require_admin(actor)
    if refund.status != "pending":
        raise ValueError("Refund must be pending")
    repository.mark_approved(refund.id)
