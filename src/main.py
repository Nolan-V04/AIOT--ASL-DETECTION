import ssl
import cv2
import numpy as np
import time
from tensorflow.keras.models import load_model
import paho.mqtt.client as mqtt
from sendImage import encode_and_publish  # Import module gửi ảnh
from emergency_email import send_emergency_alert  # Import module gửi email

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
mqtt_client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLSv1_2)
mqtt_client.tls_insecure_set(True)
mqtt_client.connect(BROKER, PORT)
mqtt_client.loop_start()

# Open camera
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

if not cap.isOpened():
    print("Cannot open camera")
    exit()

frame_counter = 0
predicted_label = '...'
last_label_sent = None
previous_time = time.time()

label_start_time = None
screenshot_taken = False
email_sent = False

clear_sentence = False
sentence_sent = False


# Sentence handling
is_recording = False
sentence = ""
confirmed_label = None
label_hold_start_time = None

while True:
    success, frame = cap.read()
    if not success:
        break

    frame_counter += 1

    roi = frame[10:234, 48:272]
    resized_img = cv2.resize(roi, (224, 224))
    normalized_img = resized_img.astype("float32") / 255.0
    input_img = np.expand_dims(normalized_img, axis=0)

    if frame_counter % 5 == 0:
        predictions = model.predict(input_img, verbose=0)
        predicted_index = np.argmax(predictions)
        predicted_label = class_names[predicted_index]
        current_time = time.time()

        # Screenshot logic for 'W'
        if predicted_label == 'W':
            if label_start_time is None:
                label_start_time = current_time
                screenshot_taken = False
            elif current_time - label_start_time >= 3 and not screenshot_taken:
                timestamp = time.strftime("%Y%m%d-%H%M%S")
                path = f"img/screenshot_{timestamp}.jpg"
                cv2.imwrite(path, frame)
                print(f"📸 Screenshot captured: {path}")
                encode_and_publish(path, mqtt_client)
                screenshot_taken = True

        # Emergency alert for 'D'
        elif predicted_label == 'D':
            if label_start_time is None:
                label_start_time = current_time
                email_sent = False
            elif current_time - label_start_time >= 3 and not email_sent:
                send_emergency_alert(predicted_label)
                email_sent = True
        
        # Sentence building
        elif predicted_label == 'B':
            if label_start_time is None:
                label_start_time = current_time
                is_recording = False
            elif current_time - label_start_time >= 3 and not is_recording:
                label_start_time = current_time
                is_recording = True
                print("🟢 Started recording.") 
            elif is_recording and current_time - label_start_time >= 3:
                is_recording = False
                print("🔴 Stopped recording.")
        elif predicted_label == 'C':
            if label_start_time is None:
                label_start_time = current_time
                clear_sentence = False
            elif current_time - label_start_time >= 3 and not clear_sentence:
                sentence = ""
                clear_sentence = True
                print("🟢 Sentence cleared.")
        elif predicted_label == 'Y':
            if label_start_time is None:
                label_start_time = current_time
                sentence_sent = False
            elif current_time - label_start_time >= 3 and not sentence_sent:
                if sentence:
                    mqtt_client.publish(TOPIC, sentence)
                    print(f"📤 Sent sentence: {sentence}")
                    sentence = ""
                else:
                    print("⚠️ No sentence to send.")
                sentence_sent = True
                is_recording = False
                confirmed_label = None
                label_hold_start_time = None
        elif predicted_label not in ['Blank', 'B', 'C', 'Y', 'W', 'D'] and is_recording:
            if predicted_label != confirmed_label:
                confirmed_label = predicted_label
                label_hold_start_time = current_time
            elif current_time - label_hold_start_time >= 3:
                sentence += confirmed_label
                print(f"📝 Added to sentence: {confirmed_label}")
                confirmed_label = None
                label_hold_start_time = None
        else:
            label_start_time = None
            screenshot_taken = False
            confirmed_label = None
            label_hold_start_time = None

        # Publish current letter (for monitoring)
        # if predicted_label != last_label_sent and not is_recording:
        #     mqtt_client.publish(TOPIC, predicted_label)
        #     last_label_sent = predicted_label

    # Drawing UI
    cv2.rectangle(frame, (48, 10), (272, 234), (0, 255, 0), 2)
    cv2.putText(frame, f'Prediction: {predicted_label}', (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 0), 2)
    cv2.putText(frame, f'Sentence: {sentence}', (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)

    fps = 1 / (time.time() - previous_time)
    previous_time = time.time()
    # cv2.putText(frame, f'FPS: {fps:.2f}', (10, 230),
    #             cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)
    if is_recording:
        cv2.putText(frame, "Recording...", (10, 90),
            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    cv2.imshow("ASL Detection", frame)
    if cv2.waitKey(1) == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
