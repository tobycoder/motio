from flask import Blueprint, current_app
from app import send_email
import logging
from app.diag import bp


@bp.get("/mail")
def diag_mail():
    cfg = current_app.config
    recipient = cfg.get("RESEND_DIAG_RECIPIENT") or cfg.get("RESEND_DEFAULT_FROM")

    if not cfg.get("RESEND_API_KEY"):
        return "MAIL ERROR: RESEND_API_KEY ontbreekt", 500
    if not recipient:
        return "MAIL ERROR: geen ontvanger ingesteld", 500

    current_app.logger.setLevel(logging.INFO)
    current_app.logger.info("Resend diag mail to %s", recipient)

    if send_email(
        subject="Diag mail",
        recipients=recipient,
        text_body="Resend testbericht — infrastructuur OK",
    ):
        return "OK: Resend mail verstuurd", 200
    return "MAIL ERROR: versturen via Resend mislukt (zie logs)", 500


@bp.get("/env")
def diag_env():
    cfg = current_app.config
    return {
        "RESEND_API_KEY_set": bool(cfg.get("RESEND_API_KEY")),
        "RESEND_DEFAULT_FROM": cfg.get("RESEND_DEFAULT_FROM"),
        "RESEND_DIAG_RECIPIENT": cfg.get("RESEND_DIAG_RECIPIENT"),
    }, 200
