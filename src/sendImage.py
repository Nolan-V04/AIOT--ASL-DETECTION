import paho.mqtt.client as mqtt
import time
import base64

# --- CẤU HÌNH MQTT (Giữ nguyên) ---
BROKER = "b3925009f3b14032b97860e7ed5a17dc.s1.eu.hivemq.cloud"
PORT = 8883
TOPIC = "glove/gesture/image_data" # Dùng topic mới cho rõ ràng
USERNAME = "htdat00111"
PASSWORD = "Aiottgmt25"

# --- KHỞI TẠO MQTT Client ---
client = mqtt.Client(client_id="python_image_sender")
client.username_pw_set(USERNAME, PASSWORD)
client.tls_set()
try:
    client.connect(BROKER, PORT)
    client.loop_start()
    print("✅ Kết nối MQTT Broker thành công!")
except Exception as e:
    print(f"❌ Lỗi kết nối MQTT: {e}")
    exit()

# --- HÀM ENCODE VÀ GỬI ---
def encode_and_publish(image_path):
    try:
        # Đọc file ảnh và encode sang Base64
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')

        # Thêm tiền tố data URI để trình duyệt có thể hiển thị ảnh
        full_base64_string = f"data:image/jpeg;base64,{encoded_string}"
        
        # Gửi thẳng chuỗi Base64 qua MQTT
        print(f"Đang gửi dữ liệu ảnh qua topic: glove/image/data")
        # MQTT có giới hạn kích thước payload, nhưng với HiveMQ Cloud free thì khá lớn (256KB)
        # Nếu ảnh của bạn lớn hơn, hãy giảm chất lượng ảnh trước khi gửi
        client.publish("glove/image/data", full_base64_string, qos=1) # Dùng QoS 1 để đảm bảo tin nhắn được gửi
        print("Gửi thành công!")

    except FileNotFoundError:
        print(f"❌ Lỗi: Không tìm thấy file ảnh '{image_path}'.")
    except Exception as e:
        print(f"Đã xảy ra lỗi khi gửi: {e}")

# --- VÒNG LẶP CHÍNH ---
# try:
#     # Chuẩn bị 1 file ảnh tên là test_image.jpg trong cùng thư mục
#     image_to_upload = 'test_image.jpg' 
#     while True:
#         encode_and_publish(image_to_upload)
#         # Tăng thời gian chờ vì gửi dữ liệu lớn tốn nhiều tài nguyên hơn
#         time.sleep(15) 
# except KeyboardInterrupt:
#     print("\nDừng chương trình.")
# finally:
#     client.loop_stop()
#     client.disconnect()
#     print("Ngắt kết nối MQTT.")