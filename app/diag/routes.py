from flask import Blueprint, current_app, request, jsonify
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
        text_body="Resend testbericht - infrastructuur OK",
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
        "ADMOTIO_API_BASE_URL": cfg.get("ADMOTIO_API_BASE_URL"),
        "ADMOTIO_CACHE_TTL": cfg.get("ADMOTIO_CACHE_TTL"),
    }, 200


@bp.get("/tenant/health")
def diag_tenant_health():
    client = current_app.extensions.get("tenant_registry_client")
    if not client:
        return {"status": "disabled"}, 200

    hostname = (request.args.get("hostname") or "").strip().lower()
    tenant_id = (request.args.get("tenant_id") or "").strip()

    result: dict[str, str | bool] = {
        "status": "ready",
        "base_url": getattr(client, "base_url", "<unknown>"),
    }

    if hostname:
        snapshot = client.get_by_hostname(hostname)
        result.update({"hostname_checked": hostname, "tenant_found": bool(snapshot)})
    elif tenant_id:
        snapshot = client.get_by_id(tenant_id)
        result.update({"tenant_id_checked": tenant_id, "tenant_found": bool(snapshot)})

    return result, 200


@bp.post("/tenant/invalidate")
def diag_tenant_invalidate():
    token_config = (current_app.config.get("ADMOTIO_WEBHOOK_TOKEN") or "").strip()
    header = request.headers.get("Authorization", "")
    incoming_token = ""
    if header.lower().startswith("bearer "):
        incoming_token = header[7:].strip()

    if token_config:
        if not incoming_token or incoming_token != token_config:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    tenant_id = (payload.get("tenant_id") or "").strip()
    hostname = (payload.get("hostname") or "").strip().lower()

    if not tenant_id and not hostname:
        return jsonify({"status": "error", "message": "tenant_id of hostname vereist"}), 400

    client = current_app.extensions.get("tenant_registry_client")
    if not client:
        current_app.logger.info("Tenant invalidatie ontvangen, maar client is niet geconfigureerd.")
        return jsonify({"status": "ignored", "reason": "client not configured"}), 200

    client.invalidate(tenant_id=tenant_id or None, hostname=hostname or None)
    if tenant_id:
        client.get_by_id(tenant_id)
    elif hostname:
        client.get_by_hostname(hostname)

    current_app.logger.info(
        "Tenant invalidatie verwerkt (tenant_id=%s hostname=%s)", tenant_id or "-", hostname or "-"
    )
    return jsonify({"status": "ok"}), 200
