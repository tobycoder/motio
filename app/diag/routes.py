from flask import Blueprint, current_app
from flask_mail import Message
from app import mail
import smtplib, logging
from app.diag import bp

@bp.get("/mail")
def diag_mail():
    cfg = current_app.config
    host = (cfg.get("MAIL_SERVER") or "").strip()
    port = int(cfg.get("MAIL_PORT") or 0)
    use_tls = bool(cfg.get("MAIL_USE_TLS"))
    use_ssl = bool(cfg.get("MAIL_USE_SSL"))
    user = cfg.get("MAIL_USERNAME")
    pwd  = cfg.get("MAIL_PASSWORD")

    current_app.logger.setLevel(logging.INFO)
    current_app.logger.info("SMTP host=%r port=%r tls=%r ssl=%r user=%r",
                            host, port, use_tls, use_ssl, user)

    if not host or host.startswith("."):
        return "MAIL ERROR: MAIL_SERVER ontbreekt of begint met een punt", 500
    if not port:
        return "MAIL ERROR: MAIL_PORT ontbreekt", 500

    try:
        if use_ssl:
            # SSL: host in constructor meegeven
            s = smtplib.SMTP_SSL(host=host, port=port, timeout=20)
            s.ehlo()
        else:
            # Plain → daarna expliciet STARTTLS als TLS aan staat
            s = smtplib.SMTP(host=host, port=port, timeout=20)
            s.ehlo()
            if use_tls:
                s.starttls()
                s.ehlo()

        if user:
            s.login(user, pwd)
        s.quit()

        # Test ook Flask-Mail
        to_addr = user or cfg.get("MAIL_DEFAULT_SENDER")
        msg = Message("Diag mail", recipients=[to_addr])
        msg.body = "SMTP + Flask-Mail werkt 🎉"
        mail.send(msg)

        return "OK: smtp + flask-mail", 200
    except Exception as e:
        current_app.logger.exception("SMTP/Flask-Mail faalde")
        return f"MAIL ERROR: {e}", 500