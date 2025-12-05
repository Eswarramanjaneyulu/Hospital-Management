from flask import Flask, render_template, request, redirect, session
import mysql.connector
import os
import razorpay
import datetime


app = Flask(__name__)
app.secret_key = "abc123"

RAZORPAY_KEY_ID = "rzp_test_xxfkdUYWCKHS4E"
RAZORPAY_KEY_SECRET = "DDFK36eIKqNL514rmiJ4vahF"

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

UPLOAD_FOLDER = "static/uploads"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Eswar@143143",
    database="hospital_db"
)
cursor = db.cursor(dictionary=True)


def clean_old_slots():
    today = datetime.date.today()

    cursor.execute("""
        DELETE FROM doctor_availability
        WHERE date < %s
    """, (today,))
    db.commit()

@app.route("/")
def home():
    return render_template("home.html")

@app.route('/patient/register', methods=['GET', 'POST'])
def patient_register():
    if request.method == "POST":
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        phone = request.form['phone']
        age = request.form['age']
        gender = request.form['gender']

        cursor.execute("""
            INSERT INTO patients (name, email, password, phone, age, gender)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (name, email, password, phone, age, gender))
        db.commit()

        return redirect('/patient/login')

    return render_template("patient_register.html")

@app.route('/doctor/register', methods=['GET', 'POST'])
def doctor_register():
    if request.method == "POST":

        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        specialization = request.form['specialization']
        experience = request.form['experience']
        phoneno = request.form['phoneno']

        photo = request.files['photo']
        filename = photo.filename
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        photo.save(filepath)

        db_path = f"static/uploads/{filename}"

        cursor.execute("""
            INSERT INTO doctors 
            (name, email, password, specialization, experience, phoneno, photo)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (name, email, password, specialization, experience, phoneno, db_path))
        db.commit()

        return "Doctor Registered Successfully!"

    return render_template("doctor_register.html")

@app.route('/patient/login', methods=['GET', 'POST'])
def patient_login():
    if request.method == "POST":

        email = request.form['email']
        password = request.form['password']

        cursor.execute("SELECT * FROM patients WHERE email=%s AND password=%s", (email, password))
        user = cursor.fetchone()

        if user:
            session['patient_id'] = user['id']
            return redirect(f"/patient/dashboard/{user['id']}")

        return "Invalid Email or Password"

    return render_template("patient_login.html")

@app.route('/doctor/login', methods=['GET', 'POST'])
def doctor_login():
    if request.method == "POST":

        email = request.form['email']
        password = request.form['password']

        cursor.execute("SELECT * FROM doctors WHERE email=%s AND password=%s", (email, password))
        doctor = cursor.fetchone()

        if doctor:
            session['doctor_id'] = doctor['id']
            return redirect(f"/doctor/dashboard/{doctor['id']}")

        return "Invalid Email or Password"

    return render_template("doctor_login.html")

@app.route('/patient/dashboard/<int:patient_id>')
def patient_dashboard(patient_id):

    clean_old_slots()  

    cursor.execute("SELECT * FROM patients WHERE id=%s", (patient_id,))
    patient = cursor.fetchone()
    cursor.execute("SELECT * FROM doctors")
    doctors = cursor.fetchall()

    cursor.execute("""
        SELECT a.id, a.date, a.slot, d.name AS doctor_name
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.patient_id = %s
        ORDER BY a.date ASC
    """, (patient_id,))

    appointments = cursor.fetchall()

    return render_template("patient_dashboard.html",
                           patient=patient,
                           doctors=doctors,
                           appointments=appointments)

@app.route('/patient/book/<int:doctor_id>', methods=['GET', 'POST'])
def patient_book(doctor_id):

    patient_id = session.get('patient_id')
    if not patient_id:
        return redirect('/patient/login')

    cursor.execute("SELECT * FROM doctors WHERE id=%s", (doctor_id,))
    doctor = cursor.fetchone()

    cursor.execute("""
        SELECT * FROM doctor_availability 
        WHERE doctor_id=%s ORDER BY date, slot
    """, (doctor_id,))
    slots = cursor.fetchall()
    
    if request.method == "POST":
        slot_id = request.form.get('slot')

        cursor.execute("SELECT * FROM doctor_availability WHERE id=%s", (slot_id,))
        selected_slot = cursor.fetchone()

        amount = 300
        amount_paise = amount * 100

        razorpay_order = razorpay_client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "payment_capture": "1"
        })

        return render_template(
            "payment_checkout.html",
            doctor=doctor,
            selected_slot=selected_slot,
            patient_id=patient_id,
            doctor_id=doctor_id,
            slot_id=slot_id,
            amount=amount,
            RAZORPAY_KEY_ID=RAZORPAY_KEY_ID,
            razorpay_order_id=razorpay_order['id']
        )

    return render_template("patient_book_appointment.html", doctor=doctor, slots=slots,patient_id=patient_id
)

@app.route('/payment/verify', methods=['POST'])
def payment_verify():

    payment_id = request.form.get("razorpay_payment_id")
    order_id = request.form.get("razorpay_order_id")
    signature = request.form.get("razorpay_signature")

    patient_id = request.form.get("patient_id")
    doctor_id = request.form.get("doctor_id")
    slot_id = request.form.get("slot_id")

    if not (payment_id and order_id and signature):
        return "Missing payment details", 400

    try:
        razorpay_client.utility.verify_payment_signature({
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature
        })
    except:
        return "Payment verification failed", 400

    cursor.execute("SELECT * FROM doctor_availability WHERE id=%s", (slot_id,))
    slot = cursor.fetchone()

    cursor.execute("""
        INSERT INTO appointments (patient_id, doctor_id, date, slot, payment_status, razorpay_payment_id)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (patient_id, doctor_id, slot['date'], slot['slot'], 'paid', payment_id))
    db.commit()

    return "Appointment booked successfully!"

@app.route('/doctor/dashboard/<int:doctor_id>')
def doctor_dashboard(doctor_id):

    clean_old_slots()  

    cursor.execute("SELECT * FROM doctors WHERE id=%s", (doctor_id,))
    doctor = cursor.fetchone()
    cursor.execute("""
        SELECT * FROM doctor_availability 
        WHERE doctor_id=%s ORDER BY date
    """, (doctor_id,))
    availability = cursor.fetchall()

    return render_template("doctor_dashboard.html",
                           doctor=doctor,
                           availability=availability)

@app.route('/doctor/set_availability/<int:doctor_id>', methods=['GET', 'POST'])
def set_availability(doctor_id):
    if request.method == "POST":
        date = request.form['date']
        selected_slots = request.form.getlist("slots")

        for slot in selected_slots:
            cursor.execute("""
                SELECT id FROM doctor_availability 
                WHERE doctor_id=%s AND date=%s AND slot=%s
            """, (doctor_id, date, slot))
            exists = cursor.fetchone()

            if exists:
                continue  

            cursor.execute("""
                INSERT INTO doctor_availability (doctor_id, date, slot)
                VALUES (%s, %s, %s)
            """, (doctor_id, date, slot))

        db.commit()
        return redirect(f"/doctor/dashboard/{doctor_id}")

    return render_template("doctor_set_availability.html", doctor_id=doctor_id)

@app.route('/doctor/appointments/<int:doctor_id>')
def doctor_appointments(doctor_id):

    cursor.execute("SELECT * FROM doctors WHERE id=%s", (doctor_id,))
    doctor = cursor.fetchone()

    cursor.execute("""
        SELECT 
            a.id, a.date, a.slot, 
            p.name AS patient_name, 
            p.phone AS patient_phone
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        WHERE a.doctor_id = %s
        ORDER BY a.date, a.slot
    """, (doctor_id,))
    appointments = cursor.fetchall()

    return render_template("doctor_appointments.html",
                           doctor=doctor,
                           appointments=appointments)


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


if __name__ == '__main__':
    app.run(debug=True)
    
    
    
    
# Set-ExecutionPolicy Unrestricted -Scope Process
# venv\Scripts\Activate.ps1