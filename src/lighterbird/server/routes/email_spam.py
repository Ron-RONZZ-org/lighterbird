"""Spam/fraud reporting REST API routes.

Provides endpoints for:
- ``POST /api/v1/email/spam/report`` — mark message as spam, fraudulent, or ham
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from lighterbird.email.service import EmailService
from lighterbird.server.deps import get_email_service

router = APIRouter(prefix="/api/v1/email/spam", tags=["email-spam"])


class SpamReportRequest(BaseModel):
    """Request body for spam/fraud/ham reporting.

    Attributes:
        uuid: Message UUID to report.
        type: ``"spam"``, ``"fraud"``, or ``"ham"``.
    """
    uuid: str = Field(..., description="Message UUID")
    type: str = Field(..., description="Report type: spam, fraud, or ham")

    model_config = {"extra": "forbid"}


@router.post("/report")
def report_spam(
    data: SpamReportRequest,
    email_svc: EmailService = Depends(get_email_service),
):
    """Report a message as spam, fraudulent, or false positive (ham).

    **Spam**: Trains the Bayesian token model, sets ``is_spam=1`` on the
    message.  The message is flagged locally; IMAP MOVE to the Spam folder is
    handled by the sync backlog.

    **Fraudulent**: Does NOT train the Bayesian model (would pollute
    token frequencies with legitimate brand names).  Instead, records
    the sender domain in the phishing watchlist and hard-deletes the
    message.

    **Ham**: Trains the Bayesian token model as NOT spam, clears
    ``is_spam``.  Use for false-positive correction.

    Args:
        data: Report request with message UUID and type.
        email_svc: Injected email service.

    Returns:
        Dict with ``status``, ``type``, and ``uuid``.

    Raises:
        HTTPException 404: Message not found.
        HTTPException 400: Invalid report type.
    """
    if data.type not in ("spam", "fraud", "ham"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid report type: {data.type}. Use 'spam', 'fraud', or 'ham'.",
        )

    # Fetch the message
    msg = email_svc.messages.get(data.uuid)
    if not msg:
        raise HTTPException(status_code=404, detail=f"Message not found: {data.uuid}")

    account_email = msg.get("account_email", "")
    subject = msg.get("subject", "") or ""
    body = msg.get("body", "") or ""

    if data.type == "spam":
        # Train Bayesian model
        spam_detect = email_svc.spam_detect
        spam_detect.trainer.report(subject, body, account_email, is_spam=True)
        spam_detect.trainer.log_feedback(data.uuid, account_email, "spam")
        # Update message flags
        email_svc.db.execute(
            "UPDATE messages SET is_spam = 1, spam_reported = 1 WHERE uuid = ?",
            (data.uuid,),
        )
        # Run classifier and store score
        result = spam_detect.classifier.classify(subject, body, account_email)
        if result["score"] is not None:
            email_svc.db.execute(
                "UPDATE messages SET spam_score = ? WHERE uuid = ?",
                (result["score"], data.uuid),
            )

    elif data.type == "fraud":
        # Phishing watchlist (does NOT train Bayesian)
        phish = email_svc.phishing
        phish.report_fraudulent(
            from_addr=msg.get("from_addr", ""),
            subject=subject,
            body=body,
            account_email=account_email,
            message_uuid=data.uuid,
        )
        # Mark message as phishing and hard-delete
        email_svc.db.execute(
            "UPDATE messages SET phishing_detected = 1, is_deleted = 1 WHERE uuid = ?",
            (data.uuid,),
        )

    elif data.type == "ham":
        # Train Bayesian as NOT spam
        spam_detect = email_svc.spam_detect
        spam_detect.trainer.report(subject, body, account_email, is_spam=False)
        spam_detect.trainer.log_feedback(data.uuid, account_email, "ham")
        # Clear spam flags
        email_svc.db.execute(
            "UPDATE messages SET is_spam = 0, spam_reported = 0, ham_reported = 1 "
            "WHERE uuid = ?",
            (data.uuid,),
        )
        # Re-classify to update score
        result = spam_detect.classifier.classify(subject, body, account_email)
        if result["score"] is not None:
            email_svc.db.execute(
                "UPDATE messages SET spam_score = ? WHERE uuid = ?",
                (result["score"], data.uuid),
            )

    return {
        "status": "ok",
        "type": data.type,
        "uuid": data.uuid,
    }
