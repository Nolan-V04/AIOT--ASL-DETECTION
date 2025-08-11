import ssl
import cv2
import numpy as np
import time
import threading
from tensorflow.keras.models import load_model
import paho.mqtt.client as mqtt
from sendImage import encode_and_publish
from emergency_email import send_emergency_alert
import json
from spellchecker import SpellChecker
spell = SpellChecker()

import tkinter as tk
from PIL import Image, ImageTk

# Load model
model = load_model("models/Final.h5")
class_names = ['B', 'C', 'D', 'E', 'H', 'I', 'K', 'L', 'O', 'Q', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Blank']

# MQTT Configuration
BROKER = "b3925009f3b14032b97860e7ed5a17dc.s1.eu.hivemq.cloud"
PORT = 8883
TOPIC = "glove/gesture/result"
USERNAME = "htdat00111"
PASSWORD = "Aiottgmt25"

mqtt_client = mqtt.Client()
mqtt_client.username_pw_set(USERNAME, PASSWORD)
mqtt_client.tls_set(cert_reqs=ssl.CERT_NONE, tls_version=ssl.PROTOCOL_TLSv1_2)
mqtt_client.tls_insecure_set(True)
mqtt_client.connect(BROKER, PORT)
mqtt_client.loop_start()

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

frame_counter = 0
predicted_label = '...'
sentence = ""
is_recording = False
status = ""
spellCheck = ""
last_label_sent = None
label_start_time = None
screenshot_taken = False
email_sent = False
clear_sentence = False
sentence_sent = False
confirmed_label = None
label_hold_start_time = None
countTimeLess = 0
countdown_start_time = None
screenshot_imgtk = None
screenshot_path = None

# Thêm biến trạng thái
waiting_for_send_image = False
y_hold_start_time = None
image_sent = False

# Thêm biến trạng thái cho gửi câu
waiting_for_send_sentence = False
sentence_y_hold_start_time = None
sentence_sent_by_y = False

# Thêm biến trạng thái cho gửi email
waiting_for_send_email = False
email_y_hold_start_time = None
email_sent_by_y = False

# Đọc emergency_letters từ file config
with open('config/emergency_config.json', 'r', encoding='utf-8') as f:
    emergency_config = json.load(f)
emergency_letters = emergency_config.get("emergency_letters", {})
emergency_labels = [k.upper() for k in emergency_letters.keys()]

# Thêm biến trạng thái cho xác nhận gửi câu
waiting_for_confirm_send_sentence = False
confirm_send_hold_start_time = None

def process_frame():
    global frame_counter, predicted_label, sentence, is_recording, status
    global label_start_time, screenshot_taken, email_sent, clear_sentence, sentence_sent
    global confirmed_label, label_hold_start_time, countTimeLess, countdown_start_time
    global screenshot_path, waiting_for_send_image, y_hold_start_time, image_sent
    global waiting_for_send_sentence, sentence_y_hold_start_time, sentence_sent_by_y
    global waiting_for_send_email, email_y_hold_start_time, email_sent_by_y
    global last_label_sent, spellCheck
    global waiting_for_confirm_send_sentence, confirm_send_hold_start_time

    success, frame = cap.read()
    if not success:
        return None, "Cannot open camera"

    frame_counter += 1
    roi = frame[10:234, 48:272]
    resized_img = cv2.resize(roi, (224, 224))
    normalized_img = resized_img.astype("float32") / 255.0
    input_img = np.expand_dims(normalized_img, axis=0)

    current_time = time.time()

    # Handle countdown for screenshot (non-blocking)
    if countdown_start_time is not None:
        elapsed = current_time - countdown_start_time
        remaining = 3 - int(elapsed)
        if remaining > 0:
            countTimeLess = remaining
        else:
            # Take screenshot
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            path = f"img/screenshot_{timestamp}.jpg"
            cv2.imwrite(path, frame)
            status = f"Đưa tay thành chữ Y để gửi ảnh."
            countTimeLess = 0
            countdown_start_time = None
            screenshot_taken = True
            screenshot_path = path
            waiting_for_send_image = True
            y_hold_start_time = None
            image_sent = False

    if frame_counter % 5 == 0:
        predictions = model.predict(input_img, verbose=0)
        predicted_index = np.argmax(predictions)
        predicted_label = class_names[predicted_index]
        current_time = time.time()

        # Nếu đang chờ gửi ảnh, chỉ xử lý label Y, W và K để thoát
        if waiting_for_send_image and screenshot_taken and screenshot_path is not None and not image_sent:
            if predicted_label == 'Y':
                if y_hold_start_time is None:
                    y_hold_start_time = current_time
                elif current_time - y_hold_start_time >= 2:
                    encode_and_publish(screenshot_path, mqtt_client)
                    status = "Đã gửi ảnh qua MQTT!"
                    screenshot_path = None
                    waiting_for_send_image = False
                    screenshot_taken = False
                    image_sent = True
                    y_hold_start_time = None
            # Giữ W để bắt đầu countdown chụp lại ảnh mới
            elif predicted_label == 'W':
                if countdown_start_time is None:
                    countdown_start_time = current_time
                    status = "Đếm ngược để chụp lại ảnh mới..."
            # Giữ K để thoát khỏi chế độ chụp ảnh mà không gửi
            elif predicted_label == 'K':
                if y_hold_start_time is None:
                    y_hold_start_time = current_time
                elif current_time - y_hold_start_time >= 2:
                    status = "Đã thoát khỏi chế độ chụp ảnh, không gửi ảnh."
                    screenshot_path = None
                    waiting_for_send_image = False
                    screenshot_taken = False
                    image_sent = False
                    y_hold_start_time = None
            else:
                y_hold_start_time = None
                label_start_time = None
            return frame, status

        # Nếu đang chờ gửi câu, cho phép nhập/xóa ký tự, giữ Y để chuyển sang xác nhận, giữ B để thoát
        if waiting_for_send_sentence and not sentence_sent_by_y:
            # Thêm ký tự vào câu nếu giữ label ký tự
            if predicted_label not in ['B', 'C', 'Y', 'Blank']:
                if predicted_label != confirmed_label:
                    confirmed_label = predicted_label
                    label_hold_start_time = current_time
                elif current_time - label_hold_start_time >= 1:
                    sentence += confirmed_label
                    status = f"Added to sentence: {confirmed_label}"
                    words = sentence.split()
                    corrected_words = [str(spell.correction(w)) if w else "" for w in words]
                    spellCheck = " ".join(corrected_words)
                    confirmed_label = None
                    label_hold_start_time = None
            # Xóa ký tự cuối nếu giữ C
            elif predicted_label == 'C':
                if label_start_time is None:
                    label_start_time = current_time
                    clear_sentence = False
                elif current_time - label_start_time >= 1.5 and not clear_sentence:
                    sentence = sentence[:-1]
                    words = sentence.split()
                    corrected_words = [str(spell.correction(w)) if w else "" for w in words]
                    spellCheck = " ".join(corrected_words)
                    clear_sentence = True
                    status = "Sentence cleared."
            # Giữ B để thoát khỏi trạng thái chờ gửi câu mà không gửi
            elif predicted_label == 'B':
                if label_start_time is None:
                    label_start_time = current_time
                elif current_time - label_start_time >= 2:
                    waiting_for_send_sentence = False
                    sentence_sent_by_y = False
                    label_start_time = None
                    status = "Đã thoát khỏi chế độ gửi câu."
            else:
                label_start_time = None
                confirmed_label = None
                label_hold_start_time = None
            if predicted_label != 'C':
                clear_sentence = False

            # Nếu giữ Y đủ 2s thì chuyển sang trạng thái xác nhận gửi câu
            if predicted_label == 'Y' and sentence:
                if sentence_y_hold_start_time is None:
                    sentence_y_hold_start_time = current_time
                elif current_time - sentence_y_hold_start_time >= 2:
                    waiting_for_confirm_send_sentence = True
                    confirm_send_hold_start_time = None
                    status = "Giữ B để gửi câu ban đầu, giữ C để gửi câu đã sửa chính tả."
                    waiting_for_send_sentence = False
                    sentence_y_hold_start_time = None
            else:
                sentence_y_hold_start_time = None

            return frame, status

        # Nếu đang chờ xác nhận gửi câu
        if waiting_for_confirm_send_sentence:
            if predicted_label == 'B' and sentence:
                if confirm_send_hold_start_time is None:
                    confirm_send_hold_start_time = current_time
                elif current_time - confirm_send_hold_start_time >= 2:
                    mqtt_client.publish(TOPIC, sentence)
                    status = "Đã gửi câu ban đầu qua MQTT!"
                    waiting_for_confirm_send_sentence = False
                    sentence_sent_by_y = True
                    confirm_send_hold_start_time = None
                    sentence = ""
            elif predicted_label == 'C' and spellCheck:
                if confirm_send_hold_start_time is None:
                    confirm_send_hold_start_time = current_time
                elif current_time - confirm_send_hold_start_time >= 2:
                    mqtt_client.publish(TOPIC, spellCheck)
                    status = "Đã gửi câu đã sửa chính tả qua MQTT!"
                    waiting_for_confirm_send_sentence = False
                    sentence_sent_by_y = True
                    confirm_send_hold_start_time = None
                    sentence = ""
            else:
                confirm_send_hold_start_time = None
            return frame, status

        # Nếu đang chờ gửi email, chỉ xử lý label trong emergency_letters hoặc Y để thoát
        if waiting_for_send_email and not email_sent_by_y:
            if predicted_label in emergency_labels:
                if email_y_hold_start_time is None or last_label_sent != predicted_label:
                    email_y_hold_start_time = current_time
                    last_label_sent = predicted_label
                elif current_time - email_y_hold_start_time >= 2:
                    send_emergency_alert(predicted_label)
                    status = f"Đã gửi email khẩn cấp với nhãn {predicted_label}!"
                    waiting_for_send_email = False
                    email_sent_by_y = True
                    email_y_hold_start_time = None
                    last_label_sent = None
            elif predicted_label == 'Y':
                if email_y_hold_start_time is None or last_label_sent != 'Y':
                    email_y_hold_start_time = current_time
                    last_label_sent = 'Y'
                elif current_time - email_y_hold_start_time >= 2:
                    status = "Đã thoát khỏi chế độ gửi email khẩn cấp."
                    waiting_for_send_email = False
                    email_sent_by_y = False
                    email_y_hold_start_time = None
                    last_label_sent = None
            else:
                email_y_hold_start_time = None
                last_label_sent = None
            return frame, status

        # Nếu không ở trạng thái chờ gửi ảnh/câu/email, xử lý các chức năng bình thường
        if predicted_label == 'W':
            if label_start_time is None:
                label_start_time = current_time
                screenshot_taken = False
            elif current_time - label_start_time >= 1.5:
                if not screenshot_taken and countdown_start_time is None:
                    countdown_start_time = current_time
        elif predicted_label == 'D':
            if label_start_time is None:
                label_start_time = current_time
                email_sent = False
            elif current_time - label_start_time >= 1.5 and not email_sent:
                waiting_for_send_email = True
                email_sent_by_y = False
                email_y_hold_start_time = None
                # Hiển thị nội dung các emergency letter
                status = ""
                for k, v in emergency_letters.items():
                    status += f"{k.upper()}: {v}\n"
                label_start_time = None
        elif predicted_label == 'B':
            if label_start_time is None:
                label_start_time = current_time
                is_recording = False
            elif current_time - label_start_time >= 1.5 and not is_recording:
                # Sau khi giữ B đủ 1.5s thì chuyển sang chờ gửi câu
                waiting_for_send_sentence = True
                sentence_sent_by_y = False
                sentence_y_hold_start_time = None
                status = "Đưa tay thành chữ Y để gửi câu."
                label_start_time = None
            elif is_recording and current_time - label_start_time >= 1.5:
                is_recording = False
                status = "Stopped recording."
        else:
            label_start_time = None
            screenshot_taken = False
            confirmed_label = None
            label_hold_start_time = None

    # Draw ROI rectangle
    cv2.rectangle(frame, (48, 10), (272, 234), (0, 255, 0), 2)
    return frame, status

class ASLApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🤟 ASL Detection UI")
        self.root.configure(bg="#23272f")
        self.root.geometry("1000x540")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Main container frame
        main_frame = tk.Frame(root, bg="#23272f")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Left frame: Camera and screenshot (fixed width)
        left_frame = tk.Frame(main_frame, bg="#23272f", width=350)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 20))
        left_frame.pack_propagate(False)

        # Video frame
        video_frame = tk.Frame(left_frame, bg="#23272f", bd=2, relief="ridge")
        video_frame.pack(pady=(0, 20))
        self.video_label = tk.Label(video_frame, bg="#23272f")
        self.video_label.pack()

        # Screenshot label
        screenshot_title = tk.Label(left_frame, text="Screenshot Preview", font=("Segoe UI", 12, "bold"),
                                   fg="#f7c873", bg="#23272f")
        screenshot_title.pack()
        self.screenshot_label = tk.Label(left_frame, bg="#23272f", width=160, height=120)
        self.screenshot_label.pack(pady=(5, 0))

        # Right frame: Info board (expand)
        right_frame = tk.Frame(main_frame, bg="#2c313c", bd=2, relief="groove")
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.prediction_var = tk.StringVar()
        self.sentence_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.recording_var = tk.StringVar()
        self.countdown_var = tk.StringVar()
        self.mode_var = tk.StringVar()
        self.spellcheck_var = tk.StringVar()

        # Title
        tk.Label(
            right_frame, text="ASL Detection", font=("Segoe UI", 22, "bold"),
            fg="#f7c873", bg="#2c313c", pady=10
        ).pack(anchor="w", padx=20, pady=(10, 20))

        # Info board content
        info_board = tk.Frame(right_frame, bg="#2c313c")
        info_board.pack(anchor="nw", padx=20, pady=10)

        # Prediction
        tk.Label(
            info_board, text="Prediction:", font=("Segoe UI", 13, "bold"),
            fg="#8ab4f8", bg="#2c313c"
        ).grid(row=0, column=0, sticky="w", padx=8, pady=5)
        tk.Label(
            info_board, textvariable=self.prediction_var, font=("Segoe UI", 18, "bold"),
            fg="#f7c873", bg="#2c313c"
        ).grid(row=0, column=1, sticky="w", padx=8, pady=5)

        # Sentence
        tk.Label(
            info_board, text="Sentence:", font=("Segoe UI", 13, "bold"),
            fg="#f7c873", bg="#2c313c"
        ).grid(row=1, column=0, sticky="w", padx=8, pady=5)
        tk.Label(
            info_board, textvariable=self.sentence_var, font=("Consolas", 15),
            fg="#e6e6e6", bg="#2c313c"
        ).grid(row=1, column=1, sticky="w", padx=8, pady=5)

        # SpellCheck (đặt ở row=2)
        tk.Label(
            info_board, text="SpellCheck:", font=("Segoe UI", 12, "italic"),
            fg="#b0e0e6", bg="#2c313c"
        ).grid(row=2, column=0, sticky="w", padx=8, pady=5)
        tk.Label(
            info_board, textvariable=self.spellcheck_var, font=("Consolas", 13, "italic"),
            fg="#b0e0e6", bg="#2c313c"
        ).grid(row=2, column=1, sticky="w", padx=8, pady=5)

        # Countdown (dịch xuống row=3)
        tk.Label(
            info_board, text="Countdown:", font=("Segoe UI", 12, "bold"),
            fg="#ffb347", bg="#2c313c"
        ).grid(row=3, column=0, sticky="w", padx=8, pady=5)
        tk.Label(
            info_board, textvariable=self.countdown_var, font=("Segoe UI", 14, "bold"),
            fg="#ffb347", bg="#2c313c"
        ).grid(row=3, column=1, sticky="w", padx=8, pady=5)

        # Mode (row=4)
        tk.Label(
            info_board, textvariable=self.mode_var, font=("Segoe UI", 13, "bold"),
            fg="#ffb347", bg="#2c313c"
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=8, pady=5)

        # Recording status (row=5)
        tk.Label(
            info_board, textvariable=self.recording_var, font=("Segoe UI", 12, "bold"),
            fg="#ff6f61", bg="#2c313c"
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=8, pady=5)

        # Status (row=6)
        tk.Label(
            info_board, textvariable=self.status_var, font=("Segoe UI", 11),
            fg="#7fffd4", bg="#2c313c"
        ).grid(row=6, column=0, columnspan=2, sticky="w", padx=8, pady=5)

        self.update_video()

    def update_video(self):
        frame, status = process_frame()
        # Cập nhật mode
        if waiting_for_send_image:
            self.mode_var.set("Mode: Screenshot")
        elif waiting_for_send_sentence:
            self.mode_var.set("Mode: Send Sentence")
        elif waiting_for_send_email:
            self.mode_var.set("Mode: Emergency Email")
        else:
            self.mode_var.set("Mode: Normal")
        if frame is not None:
            img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(img)
            imgtk = ImageTk.PhotoImage(image=img)
            self.video_label.imgtk = imgtk
            self.video_label.configure(image=imgtk)
        self.prediction_var.set(predicted_label)
        self.sentence_var.set(sentence)
        self.spellcheck_var.set(str(spellCheck) if sentence else "")
        self.status_var.set(status)
        self.recording_var.set("● Recording..." if is_recording else "")
        self.countdown_var.set(str(countTimeLess) if countTimeLess > 0 else "")  # Show countdown
        # Show screenshot preview if available
        global screenshot_imgtk, screenshot_path
        if screenshot_path is not None:
            try:
                img = Image.open(screenshot_path)
                img = img.resize((160, 120))
                screenshot_imgtk = ImageTk.PhotoImage(img)
                self.screenshot_label.config(image=screenshot_imgtk, text="")
            except Exception as e:
                self.screenshot_label.config(text="Failed to load screenshot", image="")
        else:
            self.screenshot_label.config(image="", text="")
        self.root.after(30, self.update_video)

    def on_closing(self):
        cap.release()
        cv2.destroyAllWindows()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = ASLApp(root)
    root.mainloop()

