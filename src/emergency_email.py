import smtplib
import json
from email.mime.text import MIMEText
import getpass
from datetime import datetime

def load_config():
    """Read configuration information from a JSON file."""
    try:
        with open('emergency_config.json', 'r') as file:
            config = json.load(file)
        return config.get('sender_email', ''), config.get('app_password', ''), config.get('recipients', []), config.get('emergency_letters', {})
    except FileNotFoundError:
        print("Configuration file does not exist. Please create emergency_config.json.")
        return "", "", [], {}
    except json.JSONDecodeError:
        print("Invalid configuration file. Please check it.")
        return "", "", [], {}

def save_config(sender_email, app_password, recipients, emergency_letters):
    """Save configuration information to a JSON file."""
    config = {
        "sender_email": sender_email,
        "app_password": app_password,
        "recipients": recipients,  # List of dictionaries {email, name}
        "emergency_letters": emergency_letters  # Example: {'h': 'Help', 'e': 'Emergency'}
    }
    with open('emergency_config.json', 'w') as file:
        json.dump(config, file, indent=4)
    print("Configuration has been saved.")

def send_emergency_alert(recognized_letter):
    """Send an emergency alert email based on the recognized letter."""
    sender_email, app_password, recipients, emergency_letters = load_config()

    if not sender_email or not app_password or not recipients:
        print("Configuration is incomplete. Please set up first.")
        return

    recognized_letter = recognized_letter.lower()
    emergency_desc = emergency_letters.get(recognized_letter, "Unrecognized letter")

    if recognized_letter in emergency_letters:
        for recipient in recipients:
            receiver_email = recipient.get('email', '')
            receiver_name = recipient.get('name', 'Recipient')
            if receiver_email:
                subject = f"Emergency Alert from Sign Language Device ({receiver_name})"
                body = f"Emergency! Recognized sign '{recognized_letter}' ({emergency_desc}) at {get_current_time()}."
                msg = MIMEText(body)
                msg['Subject'] = subject
                msg['From'] = sender_email
                msg['To'] = receiver_email

                try:
                    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                        server.login(sender_email, app_password)
                        server.sendmail(sender_email, receiver_email, msg.as_string())
                    print(f"Emergency email has been sent to {receiver_email}!")
                except Exception as e:
                    print(f"Error sending email to {receiver_email}: {e}")
    else:
        print(f"The letter '{recognized_letter}' is not an emergency sign.")

def get_current_time():
    """Get the current time."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def setup_config():
    """Manually set up configuration for testing."""
    sender_email = input("Enter sender email (e.g., your_email@gmail.com): ").strip()
    app_password = getpass.getpass("Enter Gmail app password: ")
    num_recipients = int(input("Enter the number of recipients: "))
    recipients = []
    for i in range(num_recipients):
        name = input(f"Enter name of recipient {i+1}: ").strip()
        email = input(f"Enter email of recipient {i+1}: ").strip()
        recipients.append({"name": name, "email": email})
    
    emergency_letters = {}
    while True:
        letter = input("Enter emergency letter (type 'exit' to finish): ").strip().lower()
        if letter == 'exit':
            break
        desc = input(f"Enter description for '{letter}' (e.g., Help): ").strip()
        emergency_letters[letter] = desc
    
    save_config(sender_email, app_password, recipients, emergency_letters)

def test_emergency_alert():
    """Test the function by entering letters in the terminal."""
    print("Enter 'setup' to configure, or enter a letter to test (type 'exit' to quit):")
    while True:
        command = input("Command/Letter: ").strip().lower()
        if command == 'exit':
            print("Test terminated.")
            break
        elif command == 'setup':
            setup_config()
        else:
            send_emergency_alert(command)
