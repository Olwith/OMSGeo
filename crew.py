import streamlit as st
import sqlite3
import folium
import time
from streamlit_folium import st_folium
from datetime import datetime
from math import radians, sin, cos, sqrt, atan2
import base64
import requests
import os
from geopy.distance import geodesic
import streamlit.components.v1 as components

# ✅ **GraphHopper API Key**
GRAPHOPPER_API_KEY = "41688daa-6df6-45fd-9623-843fab126f18"

# ✅ **Initialize Session State for Persistence**
if "crew_lat" not in st.session_state:
    st.session_state.crew_lat = None
    st.session_state.crew_lon = None

if "assigned_outage" not in st.session_state:
    st.session_state.assigned_outage = None  # Stores outage ID & coordinates

if "route" not in st.session_state:
    st.session_state.route = None  # Stores routing coordinates

# ✅ **Mobile-Friendly Settings**
def make_mobile_friendly():
    st.markdown("""
        <style>
            /* Adjust Layout */
            .block-container {
                padding: 1rem !important;
            }

            /* Increase Button & Input Field Sizes */
            button {
                font-size: 20px !important;
            }
            input {
                font-size: 18px !important;
            }

            /* Improve Scrolling for Small Screens */
            ::-webkit-scrollbar {
                display: none;
            }

            /* Adjust Table & Dataframe View */
            table {
                width: 100% !important;
                font-size: 16px !important;
            }
            
            /* Responsive Font Sizes */
            h1 { font-size: 26px !important; }
            h2 { font-size: 22px !important; }
            h3 { font-size: 20px !important; }
            h4 { font-size: 18px !important; }
            p  { font-size: 16px !important; }
            
            /* Full Width for Small Screens */
            @media (max-width: 768px) {
                .block-container {
                    max-width: 100% !important;
                    padding: 0.5rem !important;
                }
                button, input {
                    font-size: 22px !important;
                }
                table {
                    font-size: 18px !important;
                }
            }
        </style>
    """, unsafe_allow_html=True)

# ✅ **Apply Mobile Optimization**
make_mobile_friendly()

# ✅ **Database Connection**
DB_PATH = "/tmp/outage_management.db"

# ✅ Copy Database If Not Exists
if not os.path.exists(DB_PATH):
    import shutil
    shutil.copy("outage_management.db", DB_PATH)  # Copy from project folder to /tmp

# ✅ Connect to SQLite
def connect_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

# ✅ Create Tables If Not Exists
def create_tables():
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Customer (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        meter_number TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Crew (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        status TEXT DEFAULT 'Available'
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Outage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        description TEXT NOT NULL,
        report_time DATETIME DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'Pending',
        assigned_crew_id INTEGER DEFAULT NULL,
        FOREIGN KEY (customer_id) REFERENCES Customer(id),
        FOREIGN KEY (assigned_crew_id) REFERENCES Crew(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Task (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        crew_id INTEGER NOT NULL,
        outage_id INTEGER NOT NULL,
        distance REAL NOT NULL,
        eta REAL NOT NULL,
        FOREIGN KEY (crew_id) REFERENCES Crew(id),
        FOREIGN KEY (outage_id) REFERENCES Outage(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Chat (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Notification (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'unread'
    )
    """)

    conn.commit()
    conn.close()

# ✅ Ensure Tables Exist Before Running App
create_tables()

# ✅ **JavaScript to Request Location Permissions**
get_location_js = """
<script>
function requestLocation() {
    navigator.geolocation.getCurrentPosition(
        (position) => {
            const coords = position.coords.latitude + "," + position.coords.longitude;
            document.getElementById("location-data").innerText = coords;
        },
        (error) => {
            document.getElementById("location-data").innerText = "error";
        }
    );
}
</script>
<button onclick="requestLocation()">📍 Get My Location</button>
<div id="location-data">Waiting for location...</div>
"""

# ✅ Inject JavaScript in Streamlit
components.html(get_location_js, height=100)

# ✅ **Calculate Distance using Haversine formula (km)**
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371  
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

# ✅ **Function to Fetch Route from GraphHopper API**
def get_route_graphhopper():
    if st.session_state.crew_lat and st.session_state.crew_lon and st.session_state.assigned_outage:
        outage_lat = st.session_state.assigned_outage["lat"]
        outage_lon = st.session_state.assigned_outage["lon"]

        url = f"https://graphhopper.com/api/1/route?point={st.session_state.crew_lat},{st.session_state.crew_lon}&point={outage_lat},{outage_lon}&profile=car&locale=en&points_encoded=false&key={GRAPHOPPER_API_KEY}"
        response = requests.get(url)

        if response.status_code == 200:
            route_data = response.json()
            if "paths" in route_data:
                st.session_state.route = route_data["paths"][0]["points"]["coordinates"]
                st.success("✅ Route fetched successfully!")
        else:
            st.error("❌ Unable to fetch route. Check API key or network.")

# ✅ **Streamlit UI**
st.title("🚧 Crew Officer App - Task Management & Notifications")

menu = st.sidebar.radio("📍 Menu", ["Nearby Incidents", "Assigned Incidents", "Assigned Tasks", "💬 Messages", "🔔 Notifications"])

# ✅ **Nearby Incidents Section**
if menu == "Nearby Incidents":
    st.header("📍 Nearby Incidents")

    crew_id = st.number_input("Enter Crew ID:", min_value=1, step=1)

    # ✅ Ensure crew ID is valid before fetching incidents
    if crew_id:
        nearby_incidents = fetch_nearby_incidents(crew_id)
    else:
        st.error("❌ Please enter a valid Crew ID.")

    if not nearby_incidents:
        st.warning("❌ No nearby incidents available.")
    else:
        m = folium.Map(location=[-1.1018, 37.0144], zoom_start=12)

        for incident in nearby_incidents:
            outage_id, lat, lon, description, distance, customer_id = incident
            folium.Marker([lat, lon], 
                          popup=f"⚠️ Outage ID: {outage_id}\nDescription: {description}\nDistance: {distance:.2f} km", 
                          icon=folium.Icon(color="red")).add_to(m)
            st.write(f"⚠️ **Outage ID:** {outage_id} | **Description:** {description} | **Distance:** {distance:.2f} km")

            if st.button(f"🚀 Assign to Incident {outage_id}", key=f"assign_{outage_id}"):
                crew_lat, crew_lon = get_crew_location(crew_id)  # ✅ Fetch crew location

                if crew_lat is not None and crew_lon is not None:  # ✅ Ensure location exists
                   distance = round(calculate_distance(crew_lat, crew_lon, lat, lon), 2)  # ✅ Calculate distance
                   eta = round(distance / 0.5 * 10)  # ✅ Example ETA calculation (modify as needed)
                   assign_incident(crew_id, outage_id, distance, eta)  # ✅ Assign the task
                else:
                   st.error("❌ Crew location not found. Please check Crew ID.")

        st_folium(m, width=700, height=500)

# ✅ **Assigned Incidents Section**
elif menu == "Assigned Incidents":
    st.header("🛠 Assigned Incidents")

    crew_id = st.number_input("Enter Crew ID:", min_value=1, step=1)

    assigned_incidents = fetch_assigned_incidents(crew_id)

    if not assigned_incidents:
        st.warning("❌ No assigned incidents.")
    else:
        m = folium.Map(location=[-1.1018, 37.0144], zoom_start=12)

        for incident in assigned_incidents:
            outage_id, lat, lon, description, customer_id = incident
            folium.Marker([lat, lon], 
                          popup=f"✅ Assigned Task: Outage {outage_id}\nDescription: {description}", 
                          icon=folium.Icon(color="blue")).add_to(m)
            st.write(f"✅ **Assigned Task:** Outage ID {outage_id} | Description: {description}")

        st_folium(m, width=700, height=500)

# ✅ **Assigned Tasks Section**
elif menu == "Assigned Tasks":
    st.header("🛠 Assigned Tasks")
    crew_id = st.number_input("Enter Your Crew ID:", min_value=1, step=1)

    assigned_tasks = fetch_assigned_tasks(crew_id)

    if not assigned_tasks:
        st.warning("❌ No tasks assigned.")
    else:
        m = folium.Map(location=[-1.1018, 37.0144], zoom_start=12)

        for task in assigned_tasks:
            task_id, lat, lon, description, status, outage_id, distance, eta = task  # ✅ Correct unpacking

            # ✅ Show Task on Map
            folium.Marker([lat, lon], 
                          popup=f"🔧 Task ID: {task_id}\n📌 Location: ({lat}, {lon})\n📋 Description: {description}\n🟢 Status: {status}", 
                          icon=folium.Icon(color="blue" if status == "Pending" else "green")).add_to(m)

            # ✅ Task Details
            st.write(f"🔧 **Task ID:** {task_id} | **Outage ID:** {outage_id} | **Distance:** {distance:.2f} km | **ETA:** {eta:.1f} min")
            st.write(f"📋 **Description:** {description}")

            # ✅ Task Actions
            if st.button(f"⏳ Start Task {task_id}", key=f"start_{task_id}"):
                update_task_status(task_id, "In Progress", distance)
                send_notification(outage_id, f"🚀 A crew is on the way for your outage (ID: {task_id}).")
                st.success(f"✅ Task {task_id} marked as In Progress!")

            if st.button(f"✅ Mark Task {task_id} as Resolved", key=f"resolve_{task_id}"):
                update_task_status(task_id, "Resolved", distance)
                send_notification(outage_id, f"✅ Your outage (ID: {task_id}) has been resolved!")
                st.success(f"✅ Task {task_id} marked as Resolved!")

            st.write("---")

        # ✅ Display Map
        st_folium(m, width=700, height=500)

# ✅ **Notifications Section**
elif menu == "🔔 Notifications":
    st.header("🔔 Your Notifications")
    crew_id = st.number_input("Enter Your Crew ID:", min_value=1, step=1)

    notifications = fetch_unread_notifications(crew_id)
    if notifications:
        for note in notifications:
            st.write(f"📌 {note[2]}: {note[1]}")
        if st.button("✅ Mark All as Read"):
            mark_notifications_as_read(crew_id)
            st.success("✅ All notifications marked as read.")
    else:
        st.info("ℹ️ No new notifications.")

elif menu == "💬 Messages":
    st.header("💬 Chat with Customers")

    crew_id = st.number_input("Enter Your Crew ID:", min_value=1, step=1)
    assigned_customer_id = st.number_input("Enter Assigned Customer ID:", min_value=1, step=1)

    message = st.text_area("Enter your message:")

    # ✅ Send Message
    if st.button("📨 Send Message"):
        if crew_id and assigned_customer_id and message:
            send_message(crew_id, assigned_customer_id, message)
            st.success("✅ Message sent!")

    # ✅ Display Chat History
    chat_history = fetch_chat_history(crew_id)

    if chat_history:
        st.subheader("📜 Chat History")
        for msg in chat_history:
            sender, receiver, message, timestamp = msg
            sender_type = "You" if sender == crew_id else "Customer"
            st.write(f"🕒 {timestamp} - **{sender_type}:** {message}")
    else:
        st.info("ℹ️ No chat history available.")

st.subheader("📍 Crew Location Access")

# ✅ Inject JavaScript and display hidden div
location_html = components.html(get_location_js, height=50)

# ✅ Extract location from the JavaScript output
location_text = st.empty()
location = location_text.text("Waiting for location...")

# ✅ Button to Fetch Location
if st.button("📍 Get My Location"):
    # Read location from the JavaScript output
    location_value = location_text.text("Waiting for location...")  # Pass a default value
    if "," in location_value:
        lat, lon = map(float, location_value.split(","))
        st.session_state.crew_lat = lat
        st.session_state.crew_lon = lon
        st.success(f"✅ Location Updated: {lat}, {lon}")
    else:
        st.error("❌ Location access denied. Please enable GPS in browser settings.")

st.subheader("🗺️ GPS Map")

# ✅ Show map only if location is available
if st.session_state.crew_lat and st.session_state.crew_lon:
    m = folium.Map(location=[st.session_state.crew_lat, st.session_state.crew_lon], zoom_start=15)

    # ✅ Add Crew Location Marker
    folium.Marker(
        [st.session_state.crew_lat, st.session_state.crew_lon],
        popup="📍 Crew Location",
        icon=folium.Icon(color="blue")
    ).add_to(m)

    # ✅ Render the Map
    st_folium(m, width=700, height=500)
else:
    st.warning("❗ Click 'Get My Location' to enable GPS tracking.")
