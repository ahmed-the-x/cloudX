import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime
from flask import url_for




# END: SMTP Email Configuration

# The function now accepts 'app' as its first argument
def send_welcome_email(app, user_email, username):
    """Sends a fully styled, mobile-friendly welcome email with an embedded logo."""
    # Use the passed 'app' object to create an application context
    with app.app_context():
        try:
            # Create the root message
            msg = MIMEMultipart('related')
            msg['Subject'] = 'Welcome to CloudX!'
            # Access config from the passed 'app' object
            msg['From'] = app.config['MAIL_DEFAULT_SENDER'][1]
            msg['To'] = user_email

            msg_alternative = MIMEMultipart('alternative')
            msg.attach(msg_alternative)

            # --- Plain-text version ---
            text = f"""
            Hi {username},

            Welcome to CloudX, your new secure cloud storage solution.

            We're thrilled to have you on board. You can start uploading and managing your files right away by logging into your account: {url_for('login', _external=True)}

            If you have any questions or need assistance, feel free to reply to this email. We're here to help!

            Best Regards,
            The CloudX Team
            """
            
            part1 = MIMEText(text, 'plain')
            msg_alternative.attach(part1)

            # --- HTML version ---
            html = f"""
            <!DOCTYPE html>
            <html lang="en">
            <body style="margin: 0; padding: 0; background-color: #000000;">
                <div role="article" aria-roledescription="email" lang="en" class="email-container" style="width:100%; max-width:600px; margin:0 auto; background-color:#000000;">
                    <table role="presentation" style="width:100%;border:0;border-spacing:0;">
                        <tr>
                            <td align="center" style="padding:48px 32px; background-color: #000000; background-image: radial-gradient(circle at 20% 80%, rgba(120, 119, 198, 0.03) 0%, transparent 50%), radial-gradient(circle at 80% 20%, rgba(255, 255, 255, 0.02) 0%, transparent 50%);">
                                <img src="cid:logo_image" alt="CloudX Logo" style="max-width: 180px; height: auto;">
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 0 32px;">
                                <table role="presentation" style="width:100%;border:1px solid #1a1a1a;border-spacing:0;border-radius:20px; background-color:rgba(255, 255, 255, 0.02);">
                                     <tr>
                                        <td class="content-cell" style="padding:48px 40px; text-align:left;">
                                            <h2 style="font-family: 'Inter', sans-serif; font-size: 24px; font-weight: 600; color: #ffffff; margin: 0 0 24px 0;">Welcome, {username}!</h2>
                                            <p style="font-family: 'Inter', sans-serif; font-size: 16px; color: #8a8a8a; line-height: 1.6; margin: 0 0 32px 0;">
                                                We're thrilled to have you on board. You can start uploading and managing your files right away by logging into your new, secure cloud account.
                                            </p>
                                            <div style="text-align: center;">
                                                <a href="{url_for('login', _external=True)}" class="cta-button" style="background-color: #ffffff; color: #000000; border: none; padding: 16px 32px; font-size: 16px; font-weight: 600; border-radius: 50px; font-family: 'Inter', sans-serif; letter-spacing: -0.01em; text-decoration: none; display: inline-block; text-align: center;">
                                                    Access Your Cloud
                                                </a>
                                            </div>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        <tr>
                             <td align="center" style="padding:32px; border-top: 1px solid #1a1a1a;">
                                <p style="font-family: 'Inter', sans-serif; font-size: 13px; color: #8a8a8a; margin:0;">
                                For any questions, email us at <a href="mailto:{app.config['MAIL_USERNAME']}">{app.config['MAIL_USERNAME']}</a>. We're here to help!<br/>&copy; {datetime.now().year} CloudX. All Rights Reserved.
                                </p>
                            </td>
                        </tr>
                    </table>
                </div>
            </body>
            </html>
            """
            
            part2 = MIMEText(html, 'html')
            msg_alternative.attach(part2)

            # --- Embed the logo image ---
            try:
                # Use app.root_path to find the static folder relative to the app's location
                logo_path = os.path.join(app.root_path, 'static/icons/logo.png')
                with open(logo_path, 'rb') as f:
                    msg_image = MIMEImage(f.read())
                    msg_image.add_header('Content-ID', '<logo_image>')
                    msg.attach(msg_image)
            except FileNotFoundError:
                app.logger.error(f"Email logo file not found at {logo_path}")

            # Send the message
            with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
                if app.config['MAIL_USE_TLS']:
                    server.starttls()
                server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
                server.sendmail(app.config['MAIL_DEFAULT_SENDER'][1], user_email, msg.as_string())
            
            app.logger.info(f"Welcome email successfully sent to {user_email}")

        except Exception as e:
            app.logger.error(f"Failed to send welcome email to {user_email}. Error: {e}")

def send_password_reset_email(app, user_email, username, token):
    """Sends a password reset email with a unique token link."""
    with app.app_context():
        try:
            msg = MIMEMultipart('related')
            msg['Subject'] = 'Your CloudX Password Reset Request'
            msg['From'] = app.config['MAIL_DEFAULT_SENDER'][1]
            msg['To'] = user_email

            msg_alternative = MIMEMultipart('alternative')
            msg.attach(msg_alternative)
            
            reset_url = url_for('reset_with_token', token=token, _external=True)

            # --- Plain-text version ---
            text = f"""
            Hi {username},

            We received a request to reset your password for your CloudX account.

            Please click the link below to set a new password. This link is valid for one hour.
            {reset_url}

            Your verification characters are: {token}

            If you did not request a password reset, please ignore this email.

            Best Regards,
            The CloudX Team
            """
            part1 = MIMEText(text, 'plain')
            msg_alternative.attach(part1)

            # --- HTML version ---
            html = f"""
            <!DOCTYPE html>
            <html lang="en">
            <body style="margin: 0; padding: 0; background-color: #000000;">
                <div role="article" aria-roledescription="email" lang="en" class="email-container" style="width:100%; max-width:600px; margin:0 auto; background-color:#000000;">
                    <table role="presentation" style="width:100%;border:0;border-spacing:0;">
                        <tr>
                            <td align="center" style="padding:48px 32px; background-color: #000000; background-image: radial-gradient(circle at 20% 80%, rgba(120, 119, 198, 0.03) 0%, transparent 50%), radial-gradient(circle at 80% 20%, rgba(255, 255, 255, 0.02) 0%, transparent 50%);">
                                <img src="cid:logo_image" alt="CloudX Logo" style="max-width: 180px; height: auto;">
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 0 32px;">
                                <table role="presentation" style="width:100%;border:1px solid #1a1a1a;border-spacing:0;border-radius:20px; background-color:rgba(255, 255, 255, 0.02);">
                                     <tr>
                                        <td class="content-cell" style="padding:48px 40px; text-align:left;">
                                            <h2 style="font-family: 'Inter', sans-serif; font-size: 24px; font-weight: 600; color: #ffffff; margin: 0 0 24px 0;">Reset Your Password</h2>
                                            <p style="font-family: 'Inter', sans-serif; font-size: 16px; color: #8a8a8a; line-height: 1.6; margin: 0 0 16px 0;">
                                                Hi {username}, we received a request to reset your CloudX password. Click the button below to choose a new one. This link will expire in one hour.
                                            </p>
                                             <p style="font-family: 'Inter', sans-serif; font-size: 12px; color: #5a5a5a; line-height: 1.6; margin: 0 0 32px 0; word-break: break-all;">
                                                Verification Characters: {token}
                                            </p>
                                            <div style="text-align: center;">
                                                <a href="{reset_url}" class="cta-button" style="background-color: #ffffff; color: #000000; border: none; padding: 16px 32px; font-size: 16px; font-weight: 600; border-radius: 50px; font-family: 'Inter', sans-serif; letter-spacing: -0.01em; text-decoration: none; display: inline-block; text-align: center;">
                                                    Set a New Password
                                                </a>
                                            </div>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        <tr>
                             <td align="center" style="padding:32px; border-top: 1px solid #1a1a1a;">
                                <p style="font-family: 'Inter', sans-serif; font-size: 13px; color: #8a8a8a; margin:0;">
                                If you didn't request this, you can safely ignore this email. For assistance, contact <a href="mailto:{app.config['MAIL_USERNAME']}">{app.config['MAIL_USERNAME']}</a>.<br/>&copy; {datetime.now().year} CloudX. All Rights Reserved.
                                </p>
                            </td>
                        </tr>
                    </table>
                </div>
            </body>
            </html>
            """
            part2 = MIMEText(html, 'html')
            msg_alternative.attach(part2)

            # Embed the logo
            logo_path = os.path.join(app.root_path, 'static/icons/logo.png')
            with open(logo_path, 'rb') as f:
                msg_image = MIMEImage(f.read())
                msg_image.add_header('Content-ID', '<logo_image>')
                msg.attach(msg_image)

            # Send
            with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
                if app.config['MAIL_USE_TLS']:
                    server.starttls()
                server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
                server.sendmail(app.config['MAIL_DEFAULT_SENDER'][1], user_email, msg.as_string())
            
            app.logger.info(f"Password reset email successfully sent to {user_email}")

        except Exception as e:
            app.logger.error(f"Failed to send password reset email to {user_email}. Error: {e}")

def send_password_change_confirmation_email(app, user_email, username):
    """Sends an email confirming a successful password change."""
    with app.app_context():
        try:
            msg = MIMEMultipart('related')
            msg['Subject'] = 'Your CloudX Password Has Been Changed'
            msg['From'] = app.config['MAIL_DEFAULT_SENDER'][1]
            msg['To'] = user_email

            msg_alternative = MIMEMultipart('alternative')
            msg.attach(msg_alternative)

            # --- Plain-text version ---
            text = f"""
            Hi {username},

            This email confirms that the password for your CloudX account has been successfully changed.

            If you did not make this change, please contact our support team immediately by replying to this email.

            Best Regards,
            The CloudX Team
            """
            part1 = MIMEText(text, 'plain')
            msg_alternative.attach(part1)

            # --- HTML version ---
            html = f"""
            <!DOCTYPE html>
            <html lang="en">
            <body style="margin: 0; padding: 0; background-color: #000000;">
                <div role="article" aria-roledescription="email" lang="en" class="email-container" style="width:100%; max-width:600px; margin:0 auto; background-color:#000000;">
                    <table role="presentation" style="width:100%;border:0;border-spacing:0;">
                        <tr>
                            <td align="center" style="padding:48px 32px; background-color: #000000; background-image: radial-gradient(circle at 20% 80%, rgba(120, 119, 198, 0.03) 0%, transparent 50%), radial-gradient(circle at 80% 20%, rgba(255, 255, 255, 0.02) 0%, transparent 50%);">
                                <img src="cid:logo_image" alt="CloudX Logo" style="max-width: 180px; height: auto;">
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 0 32px;">
                                <table role="presentation" style="width:100%;border:1px solid #1a1a1a;border-spacing:0;border-radius:20px; background-color:rgba(255, 255, 255, 0.02);">
                                     <tr>
                                        <td class="content-cell" style="padding:48px 40px; text-align:left;">
                                            <h2 style="font-family: 'Inter', sans-serif; font-size: 24px; font-weight: 600; color: #ffffff; margin: 0 0 24px 0;">Password Changed Successfully</h2>
                                            <p style="font-family: 'Inter', sans-serif; font-size: 16px; color: #8a8a8a; line-height: 1.6; margin: 0 0 32px 0;">
                                                Hi {username}, this is a confirmation that your password for CloudX has been updated. If you didn't authorize this change, please contact support immediately.
                                            </p>
                                            <div style="text-align: center;">
                                                <a href="{url_for('login', _external=True)}" class="cta-button" style="background-color: #ffffff; color: #000000; border: none; padding: 16px 32px; font-size: 16px; font-weight: 600; border-radius: 50px; font-family: 'Inter', sans-serif; letter-spacing: -0.01em; text-decoration: none; display: inline-block; text-align: center;">
                                                    Return to Login
                                                </a>
                                            </div>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        <tr>
                             <td align="center" style="padding:32px; border-top: 1px solid #1a1a1a;">
                                <p style="font-family: 'Inter', sans-serif; font-size: 13px; color: #8a8a8a; margin:0;">
                                For any questions, email us at <a href="mailto:{app.config['MAIL_USERNAME']}">{app.config['MAIL_USERNAME']}</a>.<br/>&copy; {datetime.now().year} CloudX. All Rights Reserved.
                                </p>
                            </td>
                        </tr>
                    </table>
                </div>
            </body>
            </html>
            """
            part2 = MIMEText(html, 'html')
            msg_alternative.attach(part2)

            # Embed the logo
            logo_path = os.path.join(app.root_path, 'static/icons/logo.png')
            with open(logo_path, 'rb') as f:
                msg_image = MIMEImage(f.read())
                msg_image.add_header('Content-ID', '<logo_image>')
                msg.attach(msg_image)

            # Send
            with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
                if app.config['MAIL_USE_TLS']:
                    server.starttls()
                server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
                server.sendmail(app.config['MAIL_DEFAULT_SENDER'][1], user_email, msg.as_string())
            
            app.logger.info(f"Password change confirmation email successfully sent to {user_email}")

        except Exception as e:
            app.logger.error(f"Failed to send password change confirmation email to {user_email}. Error: {e}")

def send_contact_form_email(app, name, sender_email, subject, message):
    """Sends a contact form submission to the admin email."""
    with app.app_context():
        try:
            # Create the root message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"Contact Form: {subject}"
            # The email is sent FROM the default sender
            msg['From'] = app.config['MAIL_DEFAULT_SENDER'][1]
            # It is sent TO the admin/support email
            msg['To'] = app.config['MAIL_USERNAME']
            # IMPORTANT: This allows replying directly to the user who submitted the form
            msg.add_header('Reply-To', sender_email)

            # --- Plain-text version ---
            text = f"""
            You have received a new message from your website contact form.

            Name: {name}
            Email: {sender_email}
            Subject: {subject}

            Message:
            {message}
            """
            
            part1 = MIMEText(text, 'plain')
            msg.attach(part1)

            # --- HTML version ---
            html = f"""
            <!DOCTYPE html>
            <html>
            <body style="font-family: sans-serif; background-color: #f4f4f4; padding: 20px;">
                <div style="max-width: 600px; margin: auto; background: #ffffff; padding: 20px; border-radius: 8px;">
                    <h2 style="color: #333;">New Contact Form Submission</h2>
                    <p><strong>Subject:</strong> {subject}</p>
                    <hr>
                    <p><strong>Name:</strong> {name}</p>
                    <p><strong>Email:</strong> <a href="mailto:{sender_email}">{sender_email}</a></p>
                    <h3 style="margin-top: 20px;">Message:</h3>
                    <p style="white-space: pre-wrap; background-color: #f9f9f9; padding: 15px; border-radius: 4px;">{message}</p>
                </div>
            </body>
            </html>
            """
            
            part2 = MIMEText(html, 'html')
            msg.attach(part2)

            # Send the message
            with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
                if app.config['MAIL_USE_TLS']:
                    server.starttls()
                server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
                server.sendmail(app.config['MAIL_DEFAULT_SENDER'][1], app.config['MAIL_USERNAME'], msg.as_string())
            
            app.logger.info(f"Contact form email from {sender_email} sent successfully.")

        except Exception as e:
            app.logger.error(f"Failed to send contact form email from {sender_email}. Error: {e}")

def send_verification_email(app, user_email, username, code):
    """Sends a verification email with a 6-digit code for registration."""
    with app.app_context():
        try:
            msg = MIMEMultipart('related')
            msg['Subject'] = 'Your CloudX Verification Code'
            msg['From'] = app.config['MAIL_DEFAULT_SENDER'][1]
            msg['To'] = user_email

            msg_alternative = MIMEMultipart('alternative')
            msg.attach(msg_alternative)

            # --- Plain-text version ---
            text = f"""
            Hi {username},

            Thanks for registering with CloudX. Please use the following code to complete your registration. This code is valid for 10 minutes.

            Your verification code is: {code}

            If you did not request this, please ignore this email.

            Best Regards,
            The CloudX Team
            """
            part1 = MIMEText(text, 'plain')
            msg_alternative.attach(part1)

            # --- HTML version ---
            html = f"""
            <!DOCTYPE html>
            <html lang="en">
            <body style="margin: 0; padding: 0; background-color: #000000;">
                <div role="article" aria-roledescription="email" lang="en" class="email-container" style="width:100%; max-width:600px; margin:0 auto; background-color:#000000;">
                    <table role="presentation" style="width:100%;border:0;border-spacing:0;">
                        <tr>
                            <td align="center" style="padding:48px 32px; background-color: #000000; background-image: radial-gradient(circle at 20% 80%, rgba(120, 119, 198, 0.03) 0%, transparent 50%), radial-gradient(circle at 80% 20%, rgba(255, 255, 255, 0.02) 0%, transparent 50%);">
                                <img src="cid:logo_image" alt="CloudX Logo" style="max-width: 180px; height: auto;">
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 0 32px;">
                                <table role="presentation" style="width:100%;border:1px solid #1a1a1a;border-spacing:0;border-radius:20px; background-color:rgba(255, 255, 255, 0.02);">
                                     <tr>
                                        <td class="content-cell" style="padding:48px 40px; text-align:left;">
                                            <h2 style="font-family: 'Inter', sans-serif; font-size: 24px; font-weight: 600; color: #ffffff; margin: 0 0 24px 0;">Verify Your Email</h2>
                                            <p style="font-family: 'Inter', sans-serif; font-size: 16px; color: #8a8a8a; line-height: 1.6; margin: 0 0 32px 0;">
                                                Hi {username}, thanks for registering. Please use the code below to complete your account setup. The code will expire in 10 minutes.
                                            </p>
                                            <div style="text-align: center; background-color: #0c0c0c; border: 1px solid #2a2a2a; border-radius: 12px; padding: 24px; margin: 0 auto 32px auto;">
                                                <p style="font-family: 'Courier New', Courier, monospace; font-size: 36px; font-weight: bold; color: #ffffff; letter-spacing: 0.25em; margin: 0; text-indent: 0.25em;">
                                                    {code}
                                                </p>
                                            </div>
                                            <p style="font-family: 'Inter', sans-serif; font-size: 14px; color: #5a5a5a; text-align:center; line-height: 1.6; margin: 0;">
                                                Enter this code on the verification page to activate your account.
                                            </p>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        <tr>
                             <td align="center" style="padding:32px; border-top: 1px solid #1a1a1a;">
                                <p style="font-family: 'Inter', sans-serif; font-size: 13px; color: #8a8a8a; margin:0;">
                                If you didn't request this, you can safely ignore this email. For assistance, contact <a href="mailto:{app.config['MAIL_USERNAME']}">{app.config['MAIL_USERNAME']}</a>.<br/>&copy; {datetime.now().year} CloudX. All Rights Reserved.
                                </p>
                            </td>
                        </tr>
                    </table>
                </div>
            </body>
            </html>
            """
            part2 = MIMEText(html, 'html')
            msg_alternative.attach(part2)

            # Embed the logo
            logo_path = os.path.join(app.root_path, 'static/icons/logo.png')
            with open(logo_path, 'rb') as f:
                msg_image = MIMEImage(f.read())
                msg_image.add_header('Content-ID', '<logo_image>')
                msg.attach(msg_image)

            # Send
            with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
                if app.config['MAIL_USE_TLS']:
                    server.starttls()
                server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
                server.sendmail(app.config['MAIL_DEFAULT_SENDER'][1], user_email, msg.as_string())
            
            app.logger.info(f"Verification email successfully sent to {user_email}")

        except Exception as e:
            app.logger.error(f"Failed to send verification email to {user_email}. Error: {e}")

def send_subscription_confirmation_email(app, user_email, username, plan_name):
    """Sends an email confirming a new subscription."""
    with app.app_context():
        try:
            msg = MIMEMultipart('related')
            msg['Subject'] = f'Welcome to the {plan_name} Plan!'
            msg['From'] = app.config['MAIL_DEFAULT_SENDER'][1]
            msg['To'] = user_email

            msg_alternative = MIMEMultipart('alternative')
            msg.attach(msg_alternative)

            # --- Plain-text version ---
            text = f"""
            Hi {username},

            Thank you for subscribing to the CloudX {plan_name} plan! Your account has been successfully upgraded.

            You can now enjoy all the new features and increased storage that come with your plan.
            Access your dashboard to get started: {url_for('mycloud', _external=True)}

            We're excited to have you with us. If you have any questions, please don't hesitate to contact our support team.

            Best Regards,
            The CloudX Team
            """
            part1 = MIMEText(text, 'plain')
            msg_alternative.attach(part1)

            # --- HTML version ---
            html = f"""
            <!DOCTYPE html>
            <html lang="en">
            <body style="margin: 0; padding: 0; background-color: #000000;">
                <div role="article" aria-roledescription="email" lang="en" class="email-container" style="width:100%; max-width:600px; margin:0 auto; background-color:#000000;">
                    <table role="presentation" style="width:100%;border:0;border-spacing:0;">
                        <tr>
                            <td align="center" style="padding:48px 32px; background-color: #000000; background-image: radial-gradient(circle at 20% 80%, rgba(120, 119, 198, 0.03) 0%, transparent 50%), radial-gradient(circle at 80% 20%, rgba(255, 255, 255, 0.02) 0%, transparent 50%);">
                                <img src="cid:logo_image" alt="CloudX Logo" style="max-width: 180px; height: auto;">
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 0 32px;">
                                <table role="presentation" style="width:100%;border:1px solid #1a1a1a;border-spacing:0;border-radius:20px; background-color:rgba(255, 255, 255, 0.02);">
                                     <tr>
                                        <td class="content-cell" style="padding:48px 40px; text-align:left;">
                                            <h2 style="font-family: 'Inter', sans-serif; font-size: 24px; font-weight: 600; color: #ffffff; margin: 0 0 24px 0;">Welcome to the {plan_name} Plan!</h2>
                                            <p style="font-family: 'Inter', sans-serif; font-size: 16px; color: #8a8a8a; line-height: 1.6; margin: 0 0 32px 0;">
                                                Hi {username}, your upgrade is complete. Thank you for subscribing! You can now enjoy all the premium features, including increased storage and faster speeds.
                                            </p>
                                            <div style="text-align: center;">
                                                <a href="{url_for('mycloud', _external=True)}" class="cta-button" style="background-color: #ffffff; color: #000000; border: none; padding: 16px 32px; font-size: 16px; font-weight: 600; border-radius: 50px; font-family: 'Inter', sans-serif; letter-spacing: -0.01em; text-decoration: none; display: inline-block; text-align: center;">
                                                    Go to My Cloud
                                                </a>
                                            </div>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        <tr>
                             <td align="center" style="padding:32px; border-top: 1px solid #1a1a1a;">
                                <p style="font-family: 'Inter', sans-serif; font-size: 13px; color: #8a8a8a; margin:0;">
                                For billing questions, email us at <a href="mailto:{app.config['MAIL_USERNAME']}">{app.config['MAIL_USERNAME']}</a>.<br/>&copy; {datetime.now().year} CloudX. All Rights Reserved.
                                </p>
                            </td>
                        </tr>
                    </table>
                </div>
            </body>
            </html>
            """
            part2 = MIMEText(html, 'html')
            msg_alternative.attach(part2)

            # Embed the logo
            logo_path = os.path.join(app.root_path, 'static/icons/logo.png')
            with open(logo_path, 'rb') as f:
                msg_image = MIMEImage(f.read())
                msg_image.add_header('Content-ID', '<logo_image>')
                msg.attach(msg_image)

            # Send
            with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
                if app.config['MAIL_USE_TLS']:
                    server.starttls()
                server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
                server.sendmail(app.config['MAIL_DEFAULT_SENDER'][1], user_email, msg.as_string())
            
            app.logger.info(f"Subscription confirmation email successfully sent to {user_email}")

        except Exception as e:
            app.logger.error(f"Failed to send subscription confirmation email to {user_email}. Error: {e}")

def send_subscription_cancellation_email(app, user_email, username):
    """Sends an email confirming a subscription has been cancelled."""
    with app.app_context():
        try:
            msg = MIMEMultipart('related')
            msg['Subject'] = 'Your CloudX Subscription Has Been Cancelled'
            msg['From'] = app.config['MAIL_DEFAULT_SENDER'][1]
            msg['To'] = user_email

            msg_alternative = MIMEMultipart('alternative')
            msg.attach(msg_alternative)

            # --- Plain-text version ---
            text = f"""
            Hi {username},

            This email is to confirm that your CloudX subscription has been successfully cancelled. Your account has been downgraded to our Free plan.

            While we're sad to see you go, your files are still safe in your account. You can upgrade again at any time to regain access to premium features.
            Visit the upgrade page here: {url_for('upgrade', _external=True)}

            If you have any feedback or questions, please feel free to reply to this email.

            Best Regards,
            The CloudX Team
            """
            part1 = MIMEText(text, 'plain')
            msg_alternative.attach(part1)

            # --- HTML version ---
            html = f"""
            <!DOCTYPE html>
            <html lang="en">
            <body style="margin: 0; padding: 0; background-color: #000000;">
                <div role="article" aria-roledescription="email" lang="en" class="email-container" style="width:100%; max-width:600px; margin:0 auto; background-color:#000000;">
                    <table role="presentation" style="width:100%;border:0;border-spacing:0;">
                        <tr>
                            <td align="center" style="padding:48px 32px; background-color: #000000; background-image: radial-gradient(circle at 20% 80%, rgba(120, 119, 198, 0.03) 0%, transparent 50%), radial-gradient(circle at 80% 20%, rgba(255, 255, 255, 0.02) 0%, transparent 50%);">
                                <img src="cid:logo_image" alt="CloudX Logo" style="max-width: 180px; height: auto;">
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 0 32px;">
                                <table role="presentation" style="width:100%;border:1px solid #1a1a1a;border-spacing:0;border-radius:20px; background-color:rgba(255, 255, 255, 0.02);">
                                     <tr>
                                        <td class="content-cell" style="padding:48px 40px; text-align:left;">
                                            <h2 style="font-family: 'Inter', sans-serif; font-size: 24px; font-weight: 600; color: #ffffff; margin: 0 0 24px 0;">Subscription Cancelled</h2>
                                            <p style="font-family: 'Inter', sans-serif; font-size: 16px; color: #8a8a8a; line-height: 1.6; margin: 0 0 32px 0;">
                                                Hi {username}, this is confirmation that your CloudX subscription has been cancelled. Your account has been downgraded to the Free plan. We're sad to see you go, but you're welcome back any time.
                                            </p>
                                            <div style="text-align: center;">
                                                <a href="{url_for('upgrade', _external=True)}" class="cta-button" style="background-color: #ffffff; color: #000000; border: none; padding: 16px 32px; font-size: 16px; font-weight: 600; border-radius: 50px; font-family: 'Inter', sans-serif; letter-spacing: -0.01em; text-decoration: none; display: inline-block; text-align: center;">
                                                    View Plans
                                                </a>
                                            </div>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        <tr>
                             <td align="center" style="padding:32px; border-top: 1px solid #1a1a1a;">
                                <p style="font-family: 'Inter', sans-serif; font-size: 13px; color: #8a8a8a; margin:0;">
                                If you did this in error, please contact support at <a href="mailto:{app.config['MAIL_USERNAME']}">{app.config['MAIL_USERNAME']}</a>.<br/>&copy; {datetime.now().year} CloudX. All Rights Reserved.
                                </p>
                            </td>
                        </tr>
                    </table>
                </div>
            </body>
            </html>
            """
            part2 = MIMEText(html, 'html')
            msg_alternative.attach(part2)

            # Embed the logo
            logo_path = os.path.join(app.root_path, 'static/icons/logo.png')
            with open(logo_path, 'rb') as f:
                msg_image = MIMEImage(f.read())
                msg_image.add_header('Content-ID', '<logo_image>')
                msg.attach(msg_image)

            # Send
            with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
                if app.config['MAIL_USE_TLS']:
                    server.starttls()
                server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
                server.sendmail(app.config['MAIL_DEFAULT_SENDER'][1], user_email, msg.as_string())
            
            app.logger.info(f"Subscription cancellation email successfully sent to {user_email}")

        except Exception as e:
            app.logger.error(f"Failed to send subscription cancellation email to {user_email}. Error: {e}")

# --- NEW FUNCTION TO ADD ---

def send_public_share_link_email(app, recipient_email, share_url, filename):
    """Sends an email with the publicly generated share link."""
    with app.app_context():
        try:
            msg = MIMEMultipart('related')
            msg['Subject'] = f'Your CloudX Link for {filename}'
            msg['From'] = app.config['MAIL_DEFAULT_SENDER'][1]
            msg['To'] = recipient_email

            msg_alternative = MIMEMultipart('alternative')
            msg.attach(msg_alternative)

            # --- Plain-text version ---
            text = f"""
            Hello,

            Here is the secure CloudX link you generated for the file: {filename}

            Link: {share_url}

            This link is subject to the permissions and expiration you set.

            Best Regards,
            The CloudX Team
            """
            part1 = MIMEText(text, 'plain')
            msg_alternative.attach(part1)

            # --- HTML version ---
            html = f"""
            <!DOCTYPE html>
            <html lang="en">
            <body style="margin: 0; padding: 0; background-color: #000000;">
                <div role="article" aria-roledescription="email" lang="en" class="email-container" style="width:100%; max-width:600px; margin:0 auto; background-color:#000000;">
                    <table role="presentation" style="width:100%;border:0;border-spacing:0;">
                        <tr>
                            <td align="center" style="padding:48px 32px; background-color: #000000; background-image: radial-gradient(circle at 20% 80%, rgba(120, 119, 198, 0.03) 0%, transparent 50%), radial-gradient(circle at 80% 20%, rgba(255, 255, 255, 0.02) 0%, transparent 50%);">
                                <img src="cid:logo_image" alt="CloudX Logo" style="max-width: 180px; height: auto;">
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 0 32px;">
                                <table role="presentation" style="width:100%;border:1px solid #1a1a1a;border-spacing:0;border-radius:20px; background-color:rgba(255, 255, 255, 0.02);">
                                     <tr>
                                        <td class="content-cell" style="padding:48px 40px; text-align:left;">
                                            <h2 style="font-family: 'Inter', sans-serif; font-size: 24px; font-weight: 600; color: #ffffff; margin: 0 0 24px 0;">Here's Your Link</h2>
                                            <p style="font-family: 'Inter', sans-serif; font-size: 16px; color: #8a8a8a; line-height: 1.6; margin: 0 0 16px 0;">
                                                You requested this secure link for your file:
                                            </p>
                                            <p style="font-family: 'Inter', sans-serif; font-size: 18px; font-weight: 500; color: #ffffff; line-height: 1.6; margin: 0 0 32px 0; padding: 12px; background-color: #0c0c0c; border-radius: 8px; border: 1px solid #1a1a1a; text-align: center; word-break: break-all;">
                                                {filename}
                                            </p>
                                            <div style="text-align: center;">
                                                <a href="{share_url}" class="cta-button" style="background-color: #ffffff; color: #000000; border: none; padding: 16px 32px; font-size: 16px; font-weight: 600; border-radius: 50px; font-family: 'Inter', sans-serif; letter-spacing: -0.01em; text-decoration: none; display: inline-block; text-align: center;">
                                                    Access File
                                                </a>
                                            </div>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        <tr>
                             <td align="center" style="padding:32px; border-top: 1px solid #1a1a1a;">
                                <p style="font-family: 'Inter', sans-serif; font-size: 13px; color: #8a8a8a; margin:0;">
                                &copy; {datetime.now().year} CloudX. All Rights Reserved.
                                </p>
                            </td>
                        </tr>
                    </table>
                </div>
            </body>
            </html>
            """
            part2 = MIMEText(html, 'html')
            msg_alternative.attach(part2)

            # Embed the logo
            logo_path = os.path.join(app.root_path, 'static/icons/logo.png') 
            if not os.path.exists(logo_path):
                 logo_path = os.path.join(app.root_path, 'web-templates/static/icons/logo.png') # Fallback
            
            with open(logo_path, 'rb') as f:
                msg_image = MIMEImage(f.read())
                msg_image.add_header('Content-ID', '<logo_image>')
                msg.attach(msg_image)

            # Send
            with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
                if app.config['MAIL_USE_TLS']:
                    server.starttls()
                server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
                server.sendmail(app.config['MAIL_DEFAULT_SENDER'][1], recipient_email, msg.as_string())
            
            app.logger.info(f"Public share link email successfully sent to {recipient_email}")

        except Exception as e:
            app.logger.error(f"Failed to send public share link email to {recipient_email}. Error: {e}")