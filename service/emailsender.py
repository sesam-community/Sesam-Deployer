from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib


class Emailsender:

    def __init__(self, host, username, password, sender):
        self.password = password
        self.username = username
        self.smtphost = host
        self.sender = sender

    def send_mail(self, recipients, subject, message):
        # Create message object instance
        msg = MIMEMultipart()

        # Create message body
        message = message

        # Declare message elements
        msg['From'] = self.sender
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = subject

        msg.attach(MIMEText(str(message), 'plain'))  # Add the message body to the object instance

        server = smtplib.SMTP(self.smtphost)  # Create the server connection
        server.starttls()  # Switch the connection over to TLS encryption
        server.login(self.username, self.password)  # Authenticate with the server
        server.sendmail(msg['From'], recipients, msg.as_string())  # Send the message

        server.quit()  # Disconnect
        return "Successfully sent email {} to: {}".format(message, msg['To'])
