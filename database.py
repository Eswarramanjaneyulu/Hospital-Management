import mysql.connector

db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Eswar@143143",
    database="hospital_db"
)
cursor = db.cursor(dictionary=True)
