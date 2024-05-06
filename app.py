import firebase_admin
import bcrypt
import re
import os
from flask import Flask, render_template, request, jsonify, redirect, session
from firebase_admin import credentials, db
from dotenv import load_dotenv
from flask_mail import Mail, Message
from datetime import datetime, timedelta
import pytz
previous_data = None
sensor_enabled = True
load_dotenv()
# Khởi tạo Firebase
firebase_credentials= {
  "type": "service_account",
  "project_id": "du-bao-lu-b9c73",
   "private_key_id": os.getenv('PRIVATE_KEY_ID'),
  "private_key": os.getenv('PRIVATE_KEY').replace('\\n', '\n'),
  "client_email": "firebase-adminsdk-a4cou@du-bao-lu-b9c73.iam.gserviceaccount.com",
  "client_id": "109136797072324764500",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-a4cou%40du-bao-lu-b9c73.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}

cred = credentials.Certificate(firebase_credentials)
firebase_admin.initialize_app(cred, {
    'databaseURL': os.getenv('DATABASEURL')
})


app = Flask(__name__)
app.secret_key = os.getenv('SERECT_KEY')

# Cấu hình Flask-Mail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')

mail = Mail(app)
#..............................................................................................................................#
def send_email_alert(data):
    with app.app_context():
        users_ref = db.reference('/users')
        users_snapshot = users_ref.get()

        if users_snapshot is not None:
            for user_key, user_data in users_snapshot.items():
                username = user_data.get('username')
                email = user_data.get('email')
                
                # Kiểm tra giá trị send_email_floodwarning của người dùng
                send_email_floodwarning = user_data.get('send_email_floodwarning', False)

                # Kiểm tra xem người dùng muốn nhận email cảnh báo không
                if send_email_floodwarning:
                    msg = Message('Cảnh báo', sender='your_username@example.com', recipients=[email])
                    msg.html = render_template('email/alert_send.html', username=username, data=data)

                    try:
                        mail.send(msg)
                        print(f"Email gửi thành công tới {email}!")
                    except Exception as e:
                        print(f"Gửi email tới {email} thất bại: {e}")
                else:
                    pass

            return True
        else:
            print("Không tìm thấy người dùng trong cơ sở dữ liệu.")
            return False
#..............................................................................................................................#
@app.route("/send-data")
def save_data_to_history():
    global sensor_enabled

    vietnam_timezone = pytz.timezone('Asia/Ho_Chi_Minh')

    current_time = datetime.now(vietnam_timezone)

    current_date = current_time.strftime('%d-%m-%Y')
    current_hours = current_time.strftime('%H')
    current_minutes = current_time.strftime('%M')
    history_path = '/history/' + current_date + '/' + current_hours + '/' + current_minutes
    ref = db.reference('/data')
    history_ref = db.reference(history_path)
    data_snapshot = ref.get()
    last_data = db.reference('/last_data').get()

    if data_snapshot is not None:
        data = {
            'temp': data_snapshot.get('temp'),
            'humi': data_snapshot.get('humi'),
            'weather_temp': data_snapshot.get('weather_temp'),
            'weather_humi': data_snapshot.get('weather_humi'),
            'water_level': data_snapshot.get('water_level'),
            'prediction_water_level_1': round(float(data_snapshot.get('prediction_water_level_1')), 2),
            'prediction_water_level_2': round(float(data_snapshot.get('prediction_water_level_2')), 2),
            'caution_level': data_snapshot.get('caution_level')
        }

        if last_data != data_snapshot:
            history_ref.push(data)
            db.reference('/last_data').update(data_snapshot)
            response = {"status": "success", "message": "Cập nhật lịch sử thành công!"}
            if float(data['caution_level']) > float(data['water_level']):
                email_result = send_email_alert(data)
                if email_result:
                    response['email_status'] = "success"
                    response['email_message'] = "Gửi cảnh báo thành công!"
                else:
                    response['email_status'] = "error"
                    response['email_message'] = "Có lỗi xảy ra khi gửi cảnh báo!"
            sensor_enabled = True
        else:
            if sensor_enabled:
                response = {"status": "error", "message": "Cảm biến không được bật hoặc có lỗi xảy ra!"}
                log_path = '/log/' + current_date
                log_ref = db.reference(log_path)
                log_ref.push({
                    'timestamp': current_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'message': 'Cảm biến không được bật hoặc có lỗi xảy ra!'
                })
                sensor_enabled = False
            else:
                response = {"status": "error", "message": "Cảm biến vẫn không được bật!"}

    else:
        response = {"status": "error", "message": "Không có dữ liệu snapshot!"}

    return jsonify(response)
#..............................................................................................................................#
#Lấy dữ liệu
@app.route('/get_charts', methods=['POST'])
def get_charts():
    date = request.json['date']
    history_ref = db.reference('/history/' + date)
    history_data = history_ref.get()

    formatted_data = []

    if history_data:
        for key1, value1 in history_data.items():
            for key2, value2 in value1.items():
                for key3, value3 in value2.items():
                    formatted_data.append({
                         'date': date,
                        'time': f"{key1}:{key2}",
                        'humi': value3['humi'],
                        'temp': value3['temp'],
                        'water_level': value3['water_level']
                    })

    return jsonify(formatted_data)
#..............................................................................................................................#
@app.route('/get_history', methods=['POST'])
def get_history():
    start_date = request.json['start_date']
    end_date = request.json['end_date']

    # Convert start_date và end_date thành đối tượng datetime
    start_datetime = datetime.strptime(start_date, '%d-%m-%Y')
    end_datetime = datetime.strptime(end_date, '%d-%m-%Y')

    formatted_data = []

    # Lặp qua mỗi ngày trong khoảng thời gian và lấy dữ liệu
    while start_datetime <= end_datetime:
        date = start_datetime.strftime('%d-%m-%Y')
        history_ref = db.reference('/history/' + date)
        history_data = history_ref.get()

        if history_data:
            for key1, value1 in history_data.items():
                for key2, value2 in value1.items():
                    for key3, value3 in value2.items():
                        formatted_data.append({
                            'date': date,
                            'time': f"{key1}:{key2}",
                            'humi': value3['humi'],
                            'temp': value3['temp'],
                            'water_level': value3['water_level']
                        })

        start_datetime += timedelta(days=1)

    return jsonify(formatted_data)


#..............................................................................................................................#
# Eror 404 not found
@app.errorhandler(404)
def page_not_found(error):
    return render_template('error/404.html'), 404
# Eror 403 access denied
@app.route("/error-403-access-denied")
def access_denited():
    return render_template('error/403.html')
#..............................................................................................................................#

#Users page
@app.route("/")
def home():
    username = session.get('username')
    return render_template('user/home.html', username=username)
#About page
@app.route("/about")
def about():
    username = session.get('username')
    return render_template('user/about.html', username=username)
#Chart page
@app.route("/charts")
def charts():
    username = session.get('username')
    return render_template('user/charts.html', username=username)
#History page
@app.route("/history")
def history():
    username = session.get('username')
    return render_template('user/history.html', username=username)
#Setting page
@app.route("/settings")
def settings():
    # Lấy username từ session
    username = session.get('username')
    if username is None:
        return render_template('user/login')
    user_ref = db.reference('users')
    user_data = user_ref.child(username).get()
    # Truyền dữ liệu người dùng vào template
    return render_template('user/settings.html',username=username, user_data=user_data)
# Admin page
@app.route("/admin")
def admin_page():
    # Kiểm tra session
    role = session.get('role')
    if role == 'admin':
        return render_template('admin/dashboard.html')
    else:
        return redirect("/error-403-access-denied")

#..............................................................................................................................#
#register
@app.route("/register", methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Xử lý logic cho request POST
        data = request.json
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')

        # Kiểm tra Username đã tồn tại
        if db.reference('users').child(username).get():
            return jsonify({'message': 'Username đã đăng ký'}), 400

        # Kiểm tra Email đã tồn tại
        if db.reference('users').order_by_child('email').equal_to(email).get():
            return jsonify({'message': 'Email đã đăng ký'}), 400
        
        # Kiểm tra định dạng email
        if not re.match(r"[^@]+@gmail\.com", email):
            return jsonify({'message': 'Email không đúng định dạng'}), 400
        
        # Kiểm tra độ dài của mật khẩu
        if len(password) < 8:
            return jsonify({'message': 'Mật khẩu tối thiểu 8 ký tự'}), 400

        # Thêm người dùng vào cơ sở dữ liệu
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        role = 'user'
        user_ref = db.reference('users').child(username)
        user_ref.set({
            'username': username,
            'email': email,
            'password': hashed_password.decode('utf-8'),
            'role': role,
            'send_email_floodwarning': False,
        })

        return jsonify({'message': 'Đăng ký thành công'}), 201
    elif request.method == 'GET':
        return render_template('auth/register.html')

#..............................................................................................................................#

@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.json
        username = data.get('username')
        password = data.get('password')
        
        if username == 'admin' and password == 'admin':
            session['role'] = 'admin'
            session['username'] = username
            return jsonify({'message': 'Đăng nhập quản trị viên thành công', 'role': 'admin', 'username': username})

        user_ref = db.reference('users').child(username).get()

        if user_ref:
            hashed_password = user_ref.get('password')
            if bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8')):
                # Lưu vào session
                role = user_ref.get('role', 'user')
                session['role'] = role
                session['username'] = username
                return jsonify({'message': 'Đăng nhập thành công', 'role': role, 'username': username})
            else:
                return jsonify({'message': 'Sai mật khẩu'})
        else:
            return jsonify({'message': 'Người dùng không tồn tại'})
    elif request.method == 'GET':
        return render_template('auth/login.html')
    else:
        return jsonify({'message': 'Phương thức không được phép'})

#..............................................................................................................................#

# logout
@app.route("/logout", methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Đăng xuất thành công'})

#..............................................................................................................................#
@app.route("/set_caution", methods=['POST'])
def set_caution():
    global water_caution_level
    if request.method == 'POST':
        data = request.json
        caution = data.get('water_level')
        print('caution:', caution)

        # Thiết lập mức cảnh báo cho mức nước
        water_caution_level = int(caution)

        return jsonify({'message': 'Thiết lập mức cảnh báo thành công'})
    else:
        return jsonify({'error': 'Phương thức không được phép'}), 405
#..............................................................................................................................#
@app.route("/update-email", methods=["POST"])
def update_email():
    username = session.get('username')
    if not username:
        return jsonify({'error': 'Người dùng chưa đăng nhập'}), 401

    user_ref = db.reference('users').child(username)
    user_data = user_ref.get()
    if not user_data:
        return jsonify({'error': 'Không tìm thấy dữ liệu người dùng'}), 404

    new_email = request.json.get('new_email')
    if not new_email:
        return jsonify({'error': 'Chưa cung cấp email mới'}), 400

    # Kiểm tra định dạng của email
    if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', new_email):
        return jsonify({'error': 'Email không đúng định dạng'}), 400

    # Kiểm tra xem email đã tồn tại trong hệ thống hay chưa
    existing_user = db.reference('users').order_by_child('email').equal_to(new_email).get()
    if existing_user:
        return jsonify({'error': 'Email đã được sử dụng bởi một tài khoản khác'}), 400

    user_ref.update({'email': new_email})

    return jsonify({'success': True, 'message': 'Cập nhật email thành công'}), 200

#..............................................................................................................................#
@app.route("/toggle-email-flood-warning", methods=["POST"])
def toggle_email_flood_warning():
    username = session.get('username')
    if not username:
        return jsonify({'error': 'Người dùng chưa đăng nhập'}), 401

    user_ref = db.reference('users').child(username)
    user_data = user_ref.get()
    if not user_data:
        return jsonify({'error': 'Không tìm thấy dữ liệu người dùng'}), 404

    current_status = user_data.get('send_email_floodwarning', False)
    new_status = not current_status

    user_ref.update({'send_email_floodwarning': new_status})

    return jsonify({'success': True, 'new_status': new_status}), 200

#..............................................................................................................................#
if __name__ == "__main__":
    app.run(debug=True)
