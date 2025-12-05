import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import getpass
import time
import threading
import os
from datetime import datetime
import json
import tempfile

try:
    from colorama import Fore, Style, init
    init(autoreset=True)
except ImportError:
    class Fore:
        GREEN = ''
        BLUE = ''
        YELLOW = ''
        RED = ''
        CYAN = ''
    class Style:
        RESET_ALL = ''

# --- Configuration ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
CHAT_SUBJECT_PREFIX = "[CHAT]"
RECEIVED_FILES_DIR = "received_files"
CHAT_HISTORY_FILE = "chat_history.json"


# --- Globals ---
stop_checking_emails = threading.Event()

def load_chat_history(user_email):
    """Loads the chat history for a specific user from a JSON file."""
    if not os.path.exists(CHAT_HISTORY_FILE):
        return {}
    try:
        with open(CHAT_HISTORY_FILE, 'r') as f:
            full_history = json.load(f)
        return full_history.get(user_email, {})
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_chat_history(user_email, user_history):
    """Saves the chat history for a specific user to a JSON file."""
    full_history = {}
    if os.path.exists(CHAT_HISTORY_FILE):
        with open(CHAT_HISTORY_FILE, 'r') as f:
            try:
                full_history = json.load(f)
            except json.JSONDecodeError:
                pass
    full_history[user_email] = user_history
    with open(CHAT_HISTORY_FILE, 'w') as f:
        json.dump(full_history, f, indent=4)

def get_unique_filepath(directory, filename):
    """Generates a unique filepath by appending a number if the file already exists."""
    base, extension = os.path.splitext(filename)
    counter = 1
    unique_filepath = os.path.join(directory, filename)
    while os.path.exists(unique_filepath):
        unique_filename = f"{base} ({counter}){extension}"
        unique_filepath = os.path.join(directory, unique_filename)
        counter += 1
    return unique_filepath, os.path.basename(unique_filepath)

def process_message(msg, user_email):
    """Processes a single email message and prints it to the console."""
    date_tuple = email.utils.parsedate_tz(msg['Date'])
    timestamp = "??:??:??"
    if date_tuple:
        local_date = datetime.fromtimestamp(email.utils.mktime_tz(date_tuple))
        timestamp = local_date.strftime("%Y-%m-%d %H:%M:%S")

    from_address = msg.get('From')
    sender_tag = Fore.GREEN + "[Friend]"
    if user_email in from_address:
        sender_tag = Fore.BLUE + "[You]"

    body = ""
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition"))
            if part.get_content_type() == "text/plain" and "attachment" not in content_disposition:
                body = part.get_payload(decode=True).decode()
            elif "attachment" in content_disposition:
                filename = part.get_filename()
                if filename:
                    attachments.append(filename)
                    if user_email not in from_address:
                        if not os.path.exists(RECEIVED_FILES_DIR):
                            os.makedirs(RECEIVED_FILES_DIR)
                        
                        filepath, unique_filename = get_unique_filepath(RECEIVED_FILES_DIR, filename)
                        with open(filepath, "wb") as f:
                            f.write(part.get_payload(decode=True))
                        print(Fore.YELLOW + f" (Downloaded attachment \"{filename}\" as \"{unique_filename}\")")
    else:
        body = msg.get_payload(decode=True).decode()

    output = f"{sender_tag} {timestamp}: {body}"
    if attachments:
        output += Fore.YELLOW + f" {{Attachments: {', '.join(attachments)}}}"
    
    print(output)

def setup_chat(user_email):
    """Guides the user to start a new chat or continue a past one."""
    print(Fore.YELLOW + "--- Gmail Chat Setup ---")
    user_history = load_chat_history(user_email)
    
    if not user_history:
        print("No past chats found for this account.")
        partner_email = input("Enter your chat partner's Gmail address to start a new chat: ")
        user_history[partner_email] = []
        save_chat_history(user_email, user_history)
        return partner_email

    print("Past chats:")
    partners = list(user_history.keys())
    for i, partner in enumerate(partners):
        print(f"{i + 1}: {partner}")
    
    while True:
        print("\nChoose an option:")
        print("1. Continue a past chat")
        print("2. Start a new chat")
        
        choice = input("Enter your choice (1 or 2): ")
        
        if choice == '1':
            try:
                partner_choice = int(input("Enter the number of the chat partner: ")) - 1
                if 0 <= partner_choice < len(partners):
                    return partners[partner_choice]
                else:
                    print(Fore.RED + "Invalid partner number. Please try again.")
            except ValueError:
                print(Fore.RED + "Invalid input. Please enter a number.")
        elif choice == '2':
            partner_email = input("Enter your chat partner's Gmail address: ")
            user_history[partner_email] = []
            save_chat_history(user_email, user_history)
            return partner_email
        else:
            print(Fore.RED + "Invalid choice. Please enter 1 or 2.")

def fetch_chat_history(user_email, app_password, partner_email, count=20):
    """Fetches the last 'count' messages from the chat history."""
    try:
        with imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT) as mail:
            mail.login(user_email, app_password)
            status, _ = mail.select('"[Gmail]/All Mail"')
            if status != 'OK':
                mail.select("inbox")

            search_criteria = f'(OR (FROM "{partner_email}") (TO "{partner_email}")) (SUBJECT "{CHAT_SUBJECT_PREFIX}")'
            status, messages = mail.search(None, search_criteria)

            if status == "OK":
                email_ids = messages[0].split()
                if not email_ids:
                    print(Fore.YELLOW + "No chat history found with this partner.")
                    return

                email_ids = email_ids[-count:]
                for uid in sorted(email_ids, key=int):
                    status, msg_data = mail.fetch(uid, "(RFC822)")
                    if status == "OK":
                        for response_part in msg_data:
                            if isinstance(response_part, tuple):
                                msg = email.message_from_bytes(response_part[1])
                                process_message(msg, user_email)
    except imaplib.IMAP4.error as e:
        print(Fore.RED + f"An IMAP error occurred while fetching chat history: {e}")
    except Exception as e:
        print(Fore.RED + f"An unexpected error occurred while fetching chat history: {e}")

def check_for_new_emails(user_email, app_password, partner_email):
    """Periodically checks for new chat messages."""
    while not stop_checking_emails.is_set():
        try:
            with imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT) as mail:
                mail.login(user_email, app_password)
                mail.select("inbox")

                search_criteria = f'(UNSEEN FROM "{partner_email}" SUBJECT "{CHAT_SUBJECT_PREFIX}")'
                status, messages = mail.search(None, search_criteria)

                if status == "OK":
                    email_ids = messages[0].split()
                    for uid in email_ids:
                        status, msg_data = mail.fetch(uid, "(RFC822)")
                        if status == "OK":
                            for response_part in msg_data:
                                if isinstance(response_part, tuple):
                                    msg = email.message_from_bytes(response_part[1])
                                    if user_email not in msg.get('From'):
                                        print("\r", end="")
                                        process_message(msg, user_email)
                                        print("> ", end="", flush=True)

            time.sleep(15)
        except imaplib.IMAP4.error as e:
            # Less verbose error for periodic checks
            time.sleep(60)
        except Exception as e:
            time.sleep(60)

def create_message(sender, recipient, subject, body, attachments=None):
    """Creates a MIME multipart message."""
    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = recipient
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    if attachments:
        for file_path in attachments:
            try:
                with open(file_path, "rb") as attachment:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename= {os.path.basename(file_path)}',
                )
                msg.attach(part)
            except FileNotFoundError:
                print(Fore.RED + f"Attachment not found: {file_path}")
                return None
    return msg

def send_email(user_email, app_password, msg):
    """Sends an email using SMTP with STARTTLS."""
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(user_email, app_password)
        server.send_message(msg)
        server.quit()
        return True
    except smtplib.SMTPException as e:
        print(Fore.RED + f"Failed to send email due to an SMTP error: {e}")
        return False
    except Exception as e:
        print(Fore.RED + f"An unexpected error occurred while sending email: {e}")
        return False

def main():
    """Main function to run the chat application."""
    user_email = input("Your Gmail address: ")
    app_password = getpass.getpass("Your Gmail App Password: ")
    
    partner_email = setup_chat(user_email)

    print(Fore.BLUE + f"\nChatting with {partner_email}. Type your message and press Enter.")
    print(Fore.BLUE + "Type '/attach' to send a file, '/history' to load more messages, '/feedback' to send feedback, or '/exit' to quit.\n")

    fetch_chat_history(user_email, app_password, partner_email)

    receiver_thread = threading.Thread(
        target=check_for_new_emails,
        args=(user_email, app_password, partner_email),
        daemon=True
    )
    receiver_thread.start()

    try:
        while True:
            message_body = input("> ")
            if not message_body:
                continue

            if message_body.lower() == '/exit':
                print(Fore.YELLOW + "Shutting down...")
                break
            
            if message_body.lower().startswith('/history'):
                parts = message_body.split()
                count = 50
                if len(parts) > 1 and parts[1].isdigit():
                    count = int(parts[1])
                fetch_chat_history(user_email, app_password, partner_email, count=count)
                continue

            if message_body.lower() == '/feedback':
                print(Fore.CYAN + "--- Feedback Mode ---")
                feedback_body = input("Please enter your feedback: ")
                
                attachments = []
                attach_choice = input("Do you want to attach any files? (y/n): ")
                if attach_choice.lower() == 'y':
                    print(Fore.YELLOW + "Enter file paths to attach (comma-separated):")
                    paths_input = input()
                    attachments = [path.strip() for path in paths_input.split(',')]

                feedback_recipient = "okkhanjodkar@gmail.com"  # Should be configurable
                feedback_subject = "[ChatApp Feedback]"

                print(Fore.YELLOW + "Sending feedback...")
                msg = create_message(user_email, feedback_recipient, feedback_subject, feedback_body, attachments)
                
                if msg and send_email(user_email, app_password, msg):
                    print(Fore.GREEN + "Feedback sent successfully. Thank you!")
                else:
                    print(Fore.RED + "Failed to send feedback.")
                
                print(Fore.BLUE + f"\n--- Resuming chat with {partner_email} ---")
                continue

            attachments = []
            if message_body.lower() == '/attach':
                print(Fore.YELLOW + "Enter file paths to attach (comma-separated):")
                paths_input = input()
                attachments = [path.strip() for path in paths_input.split(',')]
                
                print(Fore.YELLOW + "Enter your message for the file(s):")
                message_body = input()

            subject = f"{CHAT_SUBJECT_PREFIX} New message"
            msg = create_message(user_email, partner_email, subject, message_body, attachments)
            
            if send_email(user_email, app_password, msg):
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"{Fore.BLUE}[You] {timestamp}: {message_body}")
                if attachments:
                    for path in attachments:
                        print(Fore.YELLOW + f"Sent attachment: {os.path.basename(path)}")
                
                user_history = load_chat_history(user_email)
                if partner_email not in user_history:
                    user_history[partner_email] = []
                user_history[partner_email].append({"sender": "You", "message": message_body, "timestamp": datetime.now().isoformat()})
                save_chat_history(user_email, user_history)

    except KeyboardInterrupt:
        print(Fore.YELLOW + "\nShutting down...")
    finally:
        stop_checking_emails.set()
        receiver_thread.join(timeout=5)
        print(Style.RESET_ALL + "Goodbye!")

if __name__ == "__main__":
    main()