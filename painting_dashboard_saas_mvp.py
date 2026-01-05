import streamlit as st
import pandas as pd
import json
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configuration
DATA_FILE = "jobs_data.json"
MIN_REMAINING_LABOR_BY_TYPE = {
    "interior_paint_2_room": 5,
    "exterior_paint": 8,
    "interior_paint_full_house": 12,
    "commercial": 16
}

# Page config
st.set_page_config(
    page_title="Labor Risk Dashboard",
    page_icon="🎨",
    layout="wide"
)

# Helper Functions
def load_jobs():
    """Load jobs from JSON file"""
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_jobs(jobs):
    """Save jobs to JSON file"""
    with open(DATA_FILE, 'w') as f:
        json.dump(jobs, f, indent=2)

def get_tracked_hours(job):
    """Calculate tracked painting hours (total - prep)"""
    return job["total_hours_worked"] - job["prep_hours_worked"]

def get_remaining_budget(job):
    """Calculate remaining labor budget"""
    return job["labor_budget"] - get_tracked_hours(job)

def get_job_alerts(job):
    """Calculate risk alerts for a job"""
    tracked_hours = get_tracked_hours(job)
    remaining_budget = job["labor_budget"] - tracked_hours
    
    # Calculate minimum required hours
    min_required = MIN_REMAINING_LABOR_BY_TYPE.get(job["job_type"], 4)
    min_required += job["scheduled_days_remaining"] * 8  # 8hr days
    
    alerts = []
    
    # HIGH RISK: Not enough budget for days remaining
    if remaining_budget < min_required:
        alerts.append("🔴 HIGH RISK")
    # MODERATE RISK: Close to minimum
    elif remaining_budget < (min_required * 1.25):
        alerts.append("🟠 MODERATE RISK")
    
    # SILENT SCOPE BLEED: Extra work without proper tracking
    if job["extra_work_flag"] and job["extra_work_logged_hours"] > 0:
        alerts.append("🟡 SILENT SCOPE BLEED")
    
    return alerts

def get_alert_priority(alerts):
    """Return numeric priority for sorting (lower = higher priority)"""
    if "🔴 HARD STOP" in alerts:
        return 1
    elif "🟠 POINT-OF-NO-RETURN" in alerts:
        return 2
    elif "🟡 SILENT SCOPE BLEED" in alerts:
        return 3
    return 4

def send_daily_alerts(jobs):
    """Send email alert for RED and ORANGE jobs"""
    try:
        # Filter jobs with RED or ORANGE alerts
        alert_jobs = []
        for job in jobs:
            alerts = get_job_alerts(job)
            if "🔴 HARD STOP" in alerts or "🟠 POINT-OF-NO-RETURN" in alerts:
                alert_jobs.append({**job, "alerts": alerts})
        
        if not alert_jobs:
            return "✅ No critical alerts to send"
        
        # Build email content
        subject = f"⚠️ Daily Labor Risk Alert - {len(alert_jobs)} Job(s) Need Attention"
        
        body = f"""
        <h2>Labor Risk Alert - {datetime.now().strftime('%A, %B %d, %Y')}</h2>
        <p><strong>{len(alert_jobs)} job(s) require immediate attention:</strong></p>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%;">
            <tr style="background-color: #f2f2f2;">
                <th>Job ID</th>
                <th>Type</th>
                <th>Budget</th>
                <th>Tracked Hrs</th>
                <th>Remaining</th>
                <th>Days Left</th>
                <th>Alerts</th>
            </tr>
        """
        
        for job in sorted(alert_jobs, key=lambda x: get_alert_priority(x["alerts"])):
            tracked = get_tracked_hours(job)
            remaining = get_remaining_budget(job)
            alert_text = " | ".join(job["alerts"])
            
            body += f"""
            <tr>
                <td>{job['job_id']}</td>
                <td>{job['job_type'].replace('_', ' ').title()}</td>
                <td>{job['labor_budget']}h</td>
                <td>{tracked}h</td>
                <td>{remaining}h</td>
                <td>{job['scheduled_days_remaining']}</td>
                <td>{alert_text}</td>
            </tr>
            """
        
        body += """
        </table>
        <p><strong>Action Required:</strong> Call foremen on RED jobs immediately.</p>
        <p>—<br>Labor Risk Dashboard</p>
        """
        
        # Get email credentials from Streamlit secrets
        email_from = st.secrets.get("EMAIL_FROM", "")
        email_password = st.secrets.get("EMAIL_PASSWORD", "")
        email_to = st.secrets.get("EMAIL_TO", "")
        
        if not all([email_from, email_password, email_to]):
            return "⚠️ Email credentials not configured in secrets"
        
        # Send email
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = email_from
        msg['To'] = email_to
        msg.attach(MIMEText(body, 'html'))
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(email_from, email_password)
            server.send_message(msg)
        
        return f"✅ Alert sent for {len(alert_jobs)} job(s)"
        
    except Exception as e:
        return f"❌ Error sending email: {str(e)}"

# Initialize sample data if file doesn't exist
if not load_jobs():
    sample_jobs = [
        {
            "job_id": "J001",
            "job_type": "interior_paint_2_room",
            "labor_budget": 32,
            "total_hours_worked": 28,
            "prep_hours_worked": 6,
            "scheduled_days_remaining": 2,
            "extra_work_flag": False,
            "extra_work_logged_hours": 0,
            "start_date": "2026-01-04"
        },
        {
            "job_id": "J002",
            "job_type": "exterior_paint",
            "labor_budget": 60,
            "total_hours_worked": 45,
            "prep_hours_worked": 8,
            "scheduled_days_remaining": 3,
            "extra_work_flag": False,
            "extra_work_logged_hours": 0,
            "start_date": "2026-01-02"
        },
        {
            "job_id": "J003",
            "job_type": "interior_paint_full_house",
            "labor_budget": 80,
            "total_hours_worked": 55,
            "prep_hours_worked": 10,
            "scheduled_days_remaining": 4,
            "extra_work_flag": True,
            "extra_work_logged_hours": 8,
            "start_date": "2025-12-28"
        }
    ]
    save_jobs(sample_jobs)

# Main App
st.title("🎨 Painting Jobs Labor Risk Dashboard")
st.markdown("**Daily Question:** *Which jobs are about to lose me money on labor?*")

# Load current jobs
jobs = load_jobs()

# Calculate metrics
red_count = sum(1 for job in jobs if "🔴 HARD STOP" in get_job_alerts(job))
orange_count = sum(1 for job in jobs if "🟠 POINT-OF-NO-RETURN" in get_job_alerts(job))
yellow_count = sum(1 for job in jobs if "🟡 SILENT SCOPE BLEED" in get_job_alerts(job))

# Top Metrics Row
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("🔴 HARD STOP", red_count)
with col2:
    st.metric("🟠 POINT-OF-NO-RETURN", orange_count)
with col3:
    st.metric("🟡 SILENT SCOPE BLEED", yellow_count)

st.markdown("---")

# Dashboard Table
if jobs:
    # Prepare table data
    table_data = []
    for job in jobs:
        tracked = get_tracked_hours(job)
        remaining = get_remaining_budget(job)
        alerts = get_job_alerts(job)
        
        table_data.append({
            "Job ID": job["job_id"],
            "Type": job["job_type"].replace("_", " ").title(),
            "Budget": f"{job['labor_budget']}h",
            "Total Hrs": f"{job['total_hours_worked']}h",
            "Prep Hrs": f"{job['prep_hours_worked']}h",
            "Tracked Painting": f"{tracked}h",
            "Remaining": f"{remaining}h",
            "Days Left": job["scheduled_days_remaining"],
            "Extra Work": f"{job['extra_work_logged_hours']}h" if job['extra_work_flag'] else "—",
            "Alerts": " | ".join(alerts) if alerts else "✅ On Track",
            "priority": get_alert_priority(alerts)
        })
    
    # Sort by priority
    table_data.sort(key=lambda x: x["priority"])
    
    # Remove priority column before display
    for row in table_data:
        del row["priority"]
    
    # Display table
    df = pd.DataFrame(table_data)
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("No jobs yet. Add your first job using the sidebar.")

# Daily Email Alert Button
st.markdown("---")
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    if st.button("📧 SEND DAILY ALERTS NOW", use_container_width=True):
        result = send_daily_alerts(jobs)
        if "✅" in result:
            st.success(result)
        else:
            st.warning(result)

# Sidebar - Job Entry Form
st.sidebar.header("➕ Add/Update Job")

with st.sidebar.form("job_form"):
    job_id = st.text_input("Job ID", placeholder="J001")
    
    job_type = st.selectbox(
        "Job Type",
        ["interior_paint_2_room", "exterior_paint", "interior_paint_full_house", "commercial"]
    )
    
    labor_budget = st.number_input("Painting Labor Budget (hours)", min_value=1, value=32)
    
    st.markdown("**Hours Tracking**")
    total_hours = st.number_input("Total Hours Worked", min_value=0, value=0)
    prep_hours = st.number_input("Prep Hours (separate billing)", min_value=0, value=0)
    
    # Live preview
    tracked_preview = total_hours - prep_hours
    remaining_preview = labor_budget - tracked_preview
    st.markdown(f"→ **Tracked Painting:** {tracked_preview}h (auto-calculated)")
    st.markdown(f"→ **Remaining Budget:** {remaining_preview}h (live preview)")
    
    days_remaining = st.number_input("Scheduled Days Remaining", min_value=0, value=1)
    
    extra_work_flag = st.checkbox("Extra Work Flagged?")
    extra_work_hours = st.number_input("Extra Work Hours", min_value=0, value=0) if extra_work_flag else 0
    
    submitted = st.form_submit_button("💾 SAVE JOB", use_container_width=True)
    
    if submitted:
        if not job_id:
            st.error("Job ID is required")
        else:
            new_job = {
                "job_id": job_id,
                "job_type": job_type,
                "labor_budget": labor_budget,
                "total_hours_worked": total_hours,
                "prep_hours_worked": prep_hours,
                "scheduled_days_remaining": days_remaining,
                "extra_work_flag": extra_work_flag,
                "extra_work_logged_hours": extra_work_hours,
                "start_date": datetime.now().strftime("%Y-%m-%d")
            }
            
            # Update existing or add new
            jobs = load_jobs()
            existing_idx = next((i for i, j in enumerate(jobs) if j["job_id"] == job_id), None)
            
            if existing_idx is not None:
                jobs[existing_idx] = new_job
                st.success(f"✅ Updated job {job_id}")
            else:
                jobs.append(new_job)
                st.success(f"✅ Added job {job_id}")
            
            save_jobs(jobs)
            st.rerun()

# Sidebar - Alert Definitions
st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 Alert Definitions")
st.sidebar.markdown("""
**🔴 HARD STOP**  
Remaining budget < minimum required for days left

**🟠 POINT-OF-NO-RETURN**  
Remaining budget < 1.25x minimum required

**🟡 SILENT SCOPE BLEED**  
Extra work flagged + extra hours > 0
""")

# Footer
st.markdown("---")
st.caption("Labor Risk Dashboard MVP | Built for painting contractors")