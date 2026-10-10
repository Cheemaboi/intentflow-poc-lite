class RefundRepository:
    def mark_approved(self, refund_id: str) -> None:
        pass


def approve_refund(actor, refund, repository: RefundRepository) -> None:
    if refund.status != "pending":
        raise ValueError("Refund must be pending")
    repository.mark_approved(refund.id)
