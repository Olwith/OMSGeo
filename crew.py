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
from streamlit_javascript import st_javascript

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
# ✅ **Create Mobile-Optimized Map**
def create_map(center_lat, center_lon, zoom=12):
    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom, control_scale=True)

    # ✅ Adjust map size for mobile
    st_folium(m, width=400 if st.session_state.get("mobile_view") else 700, height=500)



# ✅ **Database Connection**
DB_PATH = "/tmp/outage_management.db"  # Use /tmp instead of local paths
conn = sqlite3.connect(DB_PATH, check_same_thread=False)

# ✅ **Function to Get Crew GPS Location using HTML5 Geolocation**
import streamlit.components.v1 as components

# ✅ JavaScript to Request Location Permissions
get_location_js = """
<script>
function requestLocation() {
    navigator.geolocation.getCurrentPosition(
        (position) => {
            document.getElementById("location-data").innerText = 
                position.coords.latitude + "," + position.coords.longitude;
        },
        (error) => {
            document.getElementById("location-data").innerText = "error";
        }
    );
}
requestLocation();  // Auto-request location on page load
</script>
<div id="location-data">Waiting for location...</div>
"""

# ✅ Inject JavaScript in Streamlit
components.html(get_location_js, height=50)



# ✅ **Fetch Crew GPS Location**
get_browser_gps()


# ✅ **Calculate Distance using Haversine formula (km)**
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371  
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c
# ✅ **Update Crew Location in Database**
def update_crew_location(crew_id, latitude, longitude):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE Crew SET latitude = ?, longitude = ? WHERE id = ?", (latitude, longitude, crew_id))
    conn.commit()
    conn.close()
    st.success("✅ GPS Location Updated!")

# ✅ **Get Crew Location from Database**
def get_crew_location(crew_id):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT latitude, longitude FROM Crew WHERE id = ?", (crew_id,))
    crew_location = cursor.fetchone()
    conn.close()
    return crew_location if crew_location else (None, None)
# ✅ **Fetch Outage Location**
def get_outage_location(outage_id):
    conn = connect_db()
    cursor = conn.cursor()
    
    # ✅ Fetch latitude & longitude of the customer linked to the outage
    cursor.execute("""
        SELECT latitude, longitude FROM Customer 
        WHERE id = (SELECT customer_id FROM Outage WHERE id = ?)
    """, (outage_id,))
    
    outage_location = cursor.fetchone()
    conn.close()
    
    if outage_location:
        return outage_location[0],outage_location[1]#Return as tuple (lat,lon)
    else:
        return None,None #Prevent errors by returning none values





# ✅ **Fetch Nearby Incidents**
def fetch_nearby_incidents(crew_id):
    conn = connect_db()
    cursor = conn.cursor()
    
    # ✅ Check if crew exists
    cursor.execute("SELECT latitude, longitude FROM Crew WHERE id = ?", (crew_id,))
    crew_location = cursor.fetchone()
    
    if not crew_location:
        conn.close()
        return []

    crew_lat, crew_lon = crew_location
    
    # ✅ Fetch pending incidents
    cursor.execute("""
        SELECT o.id, c.latitude, c.longitude, o.description, c.id 
        FROM Outage o
        JOIN Customer c ON o.customer_id = c.id
        WHERE o.status = 'Pending'
    """)
    outages = cursor.fetchall()
    
    nearby_outages = []
    for outage in outages:
        outage_id, lat, lon, description, customer_id = outage
        distance = calculate_distance(crew_lat, crew_lon, lat, lon)
        nearby_outages.append((outage_id, lat, lon, description, distance, customer_id))
    
    # ✅ Sort by closest distance
    nearby_outages.sort(key=lambda x: x[4])

    conn.close()
    return nearby_outages
    # ✅ **Function to Assign Outage**
def assign_outage(crew_id, outage_id):
    conn = sqlite3.connect("C:/Users/User/Desktop/outage_management.db", timeout=10, check_same_thread=False)
    cursor = conn.cursor()

    # ✅ Fetch Outage Location
    cursor.execute("SELECT latitude, longitude FROM Customer WHERE id = (SELECT customer_id FROM Outage WHERE id = ?)", (outage_id,))
    result = cursor.fetchone()

    if result:
        outage_lat, outage_lon = result
        st.session_state.assigned_outage = {"id": outage_id, "lat": outage_lat, "lon": outage_lon}

        # ✅ Update Outage Status in DB
        cursor.execute("UPDATE Outage SET assigned_crew_id = ?, status = 'Assigned' WHERE id = ?", (crew_id, outage_id))
        conn.commit()

        st.success(f"✅ Outage {outage_id} assigned successfully!")
    else:
        st.error("❌ Outage location not found.")
    
    conn.close()




# ✅ **Fetch Assigned Incidents (Not Yet Started)**
def fetch_assigned_incidents(crew_id):
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT o.id, c.latitude, c.longitude, o.description, c.id
    FROM Outage o
    JOIN Customer c ON o.customer_id = c.id
    WHERE o.assigned_crew_id = ? AND o.status = 'Assigned'
    """, (crew_id,))
    
    assigned_outages = cursor.fetchall()
    conn.close()
    
    return assigned_outages

# ✅ **Fetch Assigned Tasks (In Progress or Resolved)**
def fetch_assigned_tasks(crew_id):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT o.id, c.latitude, c.longitude, o.description, o.status, c.id, c.name 
        FROM Outage o
        JOIN Customer c ON o.customer_id = c.id
        WHERE o.assigned_crew_id = ? AND o.status IN ('In Progress', 'Resolved')
    """, (crew_id,))
    assigned_tasks = cursor.fetchall()
    conn.close()
    return assigned_tasks

# ✅ **Update Task Status**
def update_task_status(task_id, status):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE Outage SET status = ? WHERE id = ?", (status, task_id))
    conn.commit()
    conn.close()

# ✅ **Fetch Assigned Task Location**
def fetch_assigned_task_location(crew_id):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.latitude, c.longitude
        FROM Outage o
        JOIN Customer c ON o.customer_id = c.id
        WHERE o.assigned_crew_id = ? AND o.status = 'Assigned'
        LIMIT 1
    """, (crew_id,))
    task_location = cursor.fetchone()
    conn.close()
    return task_location if task_location else (None, None)
# ✅ **Fetch Crew's Assigned Task**
def fetch_assigned_task(crew_id):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT o.id, c.latitude, c.longitude, o.description 
        FROM Outage o
        JOIN Customer c ON o.customer_id = c.id
        WHERE o.assigned_crew_id = ? AND o.status = 'Assigned'
        LIMIT 1
    """, (crew_id,))
    task = cursor.fetchone()
    conn.close()
    return task if task else None

# ✅ **Update Task Status**

def assign_incident(crew_id, outage_id, distance, eta):
    conn = connect_db()
    cursor = conn.cursor()

    # ✅ Assign the incident to the crew
    cursor.execute("""
    UPDATE Outage SET assigned_crew_id = ?, status = 'Assigned'
    WHERE id = ?
    """, (crew_id, outage_id))
    
    # ✅ Insert into Task table
    cursor.execute("""
    INSERT INTO Task (crew_id, outage_id, distance, eta)
    VALUES (?, ?, ?, ?)
    """, (crew_id, outage_id, distance, eta))
def get_least_loaded_crew():
    """Finds the crew with the least number of assigned tasks."""
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT crew_id, COUNT(*) as task_count FROM Task
        GROUP BY crew_id
        ORDER BY task_count ASC LIMIT 1
    """)
    least_loaded_crew = cursor.fetchone()
    
    conn.close()
    return least_loaded_crew[0] if least_loaded_crew else None

def assign_incident_to_best_crew(outage_id):
    """Assigns an outage to the least loaded crew."""
    crew_id = get_least_loaded_crew()
    if crew_id:
        distance = 5.0  # Example distance, should be calculated dynamically
        eta = calculate_eta(distance)
        assign_incident(crew_id, outage_id, distance, eta)
        st.success(f"✅ Outage {outage_id} assigned to Crew {crew_id} (Balanced Workload).")
    else:
        st.error("❌ No available crew to assign.")


    conn.commit()
def get_crew_location(crew_id):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT latitude, longitude FROM Crew WHERE id = ?", (crew_id,))
    crew_location = cursor.fetchone()
    conn.close()
    return crew_location if crew_location else (None, None)  # Return None if crew not found


    # ✅ Notify the customer
    cursor.execute("SELECT customer_id FROM Outage WHERE id = ?", (outage_id,))
    customer_id = cursor.fetchone()[0]

    send_notification(customer_id, f"A crew has been assigned to your outage (ID: {outage_id}).")
    send_notification(crew_id, f"You have been assigned to an outage (ID: {outage_id}).")

    conn.close()
    st.success(f"✅ Task {outage_id} assigned successfully!")
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

# ✅ **Button to Get Route**
if st.button("🚀 Get Route to Outage"):
    get_route_graphhopper()

# ✅ **Calculate Estimated Time of Arrival (ETA)**
def calculate_eta(distance_km, speed_kmh=30):
    """
    Calculate ETA (in minutes) based on distance and speed.
    
    distance_km: Distance in kilometers
    speed_kmh: Speed in km/h (default is 30 km/h)
    """
    if speed_kmh <= 0:
        return 0  # Prevent division by zero

    time_hours = distance_km / speed_kmh  # Time in hours
    eta_minutes = round(time_hours * 60, 2)  # Convert to minutes
    return eta_minutes

def verify_task_update(task_id):
    conn = connect_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM Task WHERE id = ?", (task_id,))
    task = cursor.fetchone()
    
    conn.close()
    
    st.write(f"🔎 Updated Task: {task}")  # ✅ Display updated row in Streamlit



def update_task_status(task_id, new_status, distance):
    """
    Updates the task status and sends a notification.
    Resolves database locking by retrying if the database is locked.
    """
    max_retries = 5  # ✅ Maximum retry attempts
    for attempt in range(max_retries):
        try:
            conn = connect_db()  # ✅ Open database connection
            cursor = conn.cursor()

            # ✅ Update task status in the Task table
            cursor.execute("""
                UPDATE Task SET status = ?, distance = ?
                WHERE id = ?
            """, (new_status, distance, task_id))

            # ✅ Fetch the related outage ID
            cursor.execute("SELECT outage_id FROM Task WHERE id = ?", (task_id,))
            outage_result = cursor.fetchone()

            if outage_result:
                outage_id = outage_result[0]

                # ✅ Fetch the related customer ID
                cursor.execute("SELECT customer_id FROM Outage WHERE id = ?", (outage_id,))
                customer_result = cursor.fetchone()

                if customer_result:
                    customer_id = customer_result[0]

                    # ✅ Send notification to customer (now inside same connection)
                    cursor.execute("""
                        INSERT INTO Notification (user_id, message, status)
                        VALUES (?, ?, 'unread')
                    """, (customer_id, f"🚀 Your outage (ID: {outage_id}) is now {new_status}."))

            conn.commit()  # ✅ Commit changes
            conn.close()  # ✅ Ensure connection is closed properly
            return True  # ✅ Success, exit loop

        except sqlite3.OperationalError as e:
            if "database is locked" in str(e):
                st.warning(f"⚠️ Database locked, retrying... ({attempt + 1}/{max_retries})")
                time.sleep(1)  # ✅ Wait 1 second before retrying
            else:
                st.error(f"❌ Database error: {e}")
                return False  # ✅ Stop retrying on other errors

        finally:
            if conn:
                conn.close()  # ✅ Ensure connection is always closed

    st.error("❌ Failed to update task status after multiple retries.")
    return False  # ✅ Return failure if all retries fail


# ✅ **Fetch Assigned Tasks**
def fetch_assigned_tasks(crew_id):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, c.latitude, c.longitude, o.description, o.status, o.id, t.distance, t.eta
        FROM Task t
        JOIN Outage o ON t.outage_id = o.id
        JOIN Customer c ON o.customer_id = c.id
        WHERE t.crew_id = ?
    """, (crew_id,))
    assigned_tasks = cursor.fetchall()
    conn.close()  # ✅ Ensure connection is closed properly
    return assigned_tasks



# ✅ **Mark Task as Resolved**
def resolve_task(task_id):
    conn = connect_db()
    cursor = conn.cursor()

    # ✅ Update Task Status
    cursor.execute("UPDATE Outage SET status = 'Resolved' WHERE id = ?", (task_id,))
    conn.commit()

    # ✅ Fetch Outage ID & Notify Customer
    cursor.execute("SELECT outage_id FROM Task WHERE id = ?", (task_id,))
    outage_id = cursor.fetchone()

    if outage_id:
        notify_customer_task_resolved(outage_id[0])

    conn.close()
    st.success(f"✅ Task {task_id} marked as Resolved!")


# ✅ Send Message
def send_message(sender_id, receiver_id, message):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO Chat (sender_id, receiver_id, message, timestamp)
    VALUES (?, ?, ?, datetime('now'))
    """, (sender_id, receiver_id, message))
    conn.commit()
    conn.close()
    st.success("✅ Message sent!")

# ✅ Fetch Chat History for Crew
def fetch_chat_history(crew_id):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT sender_id, receiver_id, message, timestamp FROM Chat
    WHERE sender_id = ? OR receiver_id = ?
    ORDER BY timestamp DESC
    """, (crew_id, crew_id))
    chat_history = cursor.fetchall()
    conn.close()
    return chat_history
    from streamlit_autorefresh import st_autorefresh

    # ✅ Auto-refresh every 10 seconds instead of locking database
    st_autorefresh(interval=10 * 1000, key="chat_refresh")

    chat_history = fetch_chat_history(crew_id)  # ✅ Fetch new messages
# ✅ **Send Notification**
def send_notification(user_id, message):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO Notification (user_id, message, status) VALUES (?, ?, 'unread')
    """, (user_id, message))
    conn.commit()
    conn.close()

# ✅ Fetch Unread Notifications for Crew
def fetch_unread_notifications(crew_id):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, message, timestamp FROM Notification
    WHERE user_id = ? AND status = 'unread'
    ORDER BY timestamp DESC
    """, (crew_id,))
    notifications = cursor.fetchall()
    conn.close()
    return notifications

# ✅ **Mark Notifications as Read**
def mark_notifications_as_read(user_id):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE Notification SET status = 'read' WHERE user_id = ?
    """, (user_id,))
    conn.commit()
    conn.close()
# ✅ **Function to Send Push Notifications**
def send_notification(user_id, message):
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO Notification (user_id, message, status) VALUES (?, ?, 'unread')", (user_id, message))
    conn.commit()
    conn.close()


# ✅ **Streamlit UI**
st.title("🚧 Crew Officer App - Task Management & Notifications")

menu = st.sidebar.radio("📍 Menu", ["Nearby Incidents", "Assigned Incidents","Assigned Tasks","💬 Messages" ,"🔔 Notifications"])

# ✅ **Nearby Incidents Section**
if menu == "Nearby Incidents":
    st.header("📍 Nearby Incidents")

    crew_id = st.number_input("Enter Crew ID:", min_value=1, step=1)

    # ✅ Ensure crew ID is valid before fetching incidents
    if st.button("🔍 Show Nearby Incidents"):
        if crew_id:
            st.session_state["nearby_incidents"] = fetch_nearby_incidents(crew_id)
        else:
            st.error("❌ Please enter a valid Crew ID.")

    # ✅ Retrieve stored incidents from session state
    nearby_incidents = st.session_state.get("nearby_incidents", [])

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
                   st.session_state["nearby_incidents"] = fetch_nearby_incidents(crew_id)  # ✅ Refresh list
                else:
                   st.error("❌ Crew location not found. Please check Crew ID.")



        st_folium(m, width=700, height=500)


# ✅ **Assigned Incidents Section**
elif menu == "Assigned Incidents":
    st.header("🛠 Assigned Incidents")

    crew_id = st.number_input("Enter Crew ID:", min_value=1, step=1)

    if st.button("📋 View Assigned Incidents"):
        assigned_incidents = fetch_assigned_incidents(crew_id)
        st.session_state["assigned_incidents"] = assigned_incidents

    assigned_incidents = st.session_state.get("assigned_incidents", [])

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

    if st.button("🔄 Refresh Tasks"):
        assigned_tasks = fetch_assigned_tasks(crew_id)
        st.session_state["assigned_tasks"] = assigned_tasks

    assigned_tasks = st.session_state.get("assigned_tasks", [])

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

    if st.button("📩 Refresh Notifications"):
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

    # ✅ Refresh Chat History Button
    if st.button("🔄 Refresh Chat"):
        chat_history = fetch_chat_history(crew_id)
        st.session_state["chat_history"] = chat_history
        st.success("✅ Chat refreshed!")

    # ✅ Display Chat History
    chat_history = st.session_state.get("chat_history", fetch_chat_history(crew_id))

    if chat_history:
        st.subheader("📜 Chat History")
        for msg in chat_history:
            sender, receiver, message, timestamp = msg
            sender_type = "You" if sender == crew_id else "Customer"
            st.write(f"🕒 {timestamp} - **{sender_type}:** {message}")
    else:
        st.info("ℹ️ No chat history available.")

# ✅ **Enhanced Map UI for Crew Tracking & Routing**
st.header("🚗 Crew GPS Tracking & Routing")

if st.session_state.crew_lat and st.session_state.crew_lon:
    m = folium.Map(location=[st.session_state.crew_lat, st.session_state.crew_lon], zoom_start=15)

    # ✅ Crew Location Marker
    folium.Marker(
        [st.session_state.crew_lat, st.session_state.crew_lon], 
        popup="📍 Crew Location",
        icon=folium.Icon(color="blue")
    ).add_to(m)

    # ✅ Outage Location Marker (If Assigned)
    if st.session_state.assigned_outage:
        folium.Marker(
            [st.session_state.assigned_outage["lat"], st.session_state.assigned_outage["lon"]], 
            popup=f"⚡ Outage {st.session_state.assigned_outage['id']}",
            icon=folium.Icon(color="red")
        ).add_to(m)

        # ✅ Plot Route from GraphHopper
        if st.session_state.route:
            folium.PolyLine(
                locations=[[lat, lon] for lon, lat in st.session_state.route],
                color="blue",
                weight=5
            ).add_to(m)

    # ✅ Display Map
    st_folium(m, width=700, height=500)
else:
    st.error("❌ GPS location not found. Please enable location services.")

