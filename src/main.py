import cv2
import numpy as np
import time
from tensorflow.keras.models import load_model
import paho.mqtt.client as mqtt
from emergency_email import send_emergency_alert  # Import module gửi email

# Load model
model = load_model("models/mobilenetv2_asl_model_improved.h5")
class_names = ['A', 'B', 'C', 'H', 'L', 'O', 'Q', 'U', 'W', 'Y', 'Blank']

# MQTT Configuration
BROKER = "b3925009f3b14032b97860e7ed5a17dc.s1.eu.hivemq.cloud"
PORT = 8883
TOPIC = "glove/gesture/result"
USERNAME = "htdat00111"
PASSWORD = "Aiottgmt25"

mqtt_client = mqtt.Client()
mqtt_client.username_pw_set(USERNAME, PASSWORD)
mqtt_client.tls_set()
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
last_email_sent_time = 0  # Để tránh gửi email liên tục
email_sent = False

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

        # Chụp màn hình nếu nhận diện 'W' trong 3 giây
        if predicted_label == 'W':
            if label_start_time is None:
                label_start_time = current_time
                screenshot_taken = False
            elif current_time - label_start_time >= 3 and not screenshot_taken:
                timestamp = time.strftime("%Y%m%d-%H%M%S")
                cv2.imwrite(f"img/screenshot_{timestamp}.jpg", frame)
                print(f"📸 Screenshot captured: screenshot_{timestamp}.jpg")
                screenshot_taken = True
        elif predicted_label == 'H':
            if label_start_time is None:
                label_start_time = current_time
                email_sent = False
            elif current_time - label_start_time >= 3 and not email_sent:
                send_emergency_alert(predicted_label)
                email_sent = True
        else:
            label_start_time = None
            screenshot_taken = False

        
        # Gửi MQTT nếu label thay đổi
        if predicted_label != last_label_sent:
            mqtt_client.publish(TOPIC, predicted_label)
            last_label_sent = predicted_label

    # Vẽ giao diện
    cv2.rectangle(frame, (48, 10), (272, 234), (0, 255, 0), 2)
    cv2.putText(frame, f'Prediction: {predicted_label}', (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 0), 2)

    fps = 1 / (time.time() - previous_time)
    previous_time = time.time()
    cv2.putText(frame, f'FPS: {fps:.2f}', (10, 230),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)

    cv2.imshow("ASL Detection", frame)
    if cv2.waitKey(1) == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
