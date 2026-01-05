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

def get_crew_status(job):
    """Calculate crew-facing status (non-alert language)"""
    tracked_hours = get_tracked_hours(job)
    remaining_budget = job["labor_budget"] - tracked_hours
    
    min_required = MIN_REMAINING_LABOR_BY_TYPE.get(job["job_type"], 4)
    min_required += job["scheduled_days_remaining"] * 8
    
    runway_ratio = remaining_budget / min_required if min_required > 0 else 999
    
    if runway_ratio < 1.0:
        return "Critical", "#FF6B6B", remaining_budget
    elif runway_ratio < 1.25:
        return "Tight", "#FFA726", remaining_budget
    else:
        return "On Track", "#66BB6A", remaining_budget

def get_minimum_remaining_work(job):
    """Get list of non-negotiable work items for crew view"""
    job_type = job["job_type"]
    days = job["scheduled_days_remaining"]
    
    work_items = {
        "interior_paint_2_room": ["Final coat application", "Trim & detail work", "Touch-ups & inspection"],
        "exterior_paint": ["Final coat application", "Trim & detail work", "Cleanup & site restoration"],
        "interior_paint_full_house": ["Final coat all rooms", "Trim & doors", "Touch-ups & walkthrough"],
        "commercial": ["Final coat application", "Detail work", "Site cleanup", "Client walkthrough"]
    }
    
    base_work = work_items.get(job_type, ["Final coat", "Details", "Cleanup"])
    
    if days > 0:
        base_work.append(f"{days} full day(s) scheduled")
    
    return base_work
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
    if "🔴 HIGH RISK" in alerts:
        return 1
    elif "🟠 MODERATE RISK" in alerts:
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
            if "🔴 HIGH RISK" in alerts or "🟠 MODERATE RISK" in alerts:
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

# View Toggle
view_mode = st.radio(
    "View Mode",
    ["Owner Dashboard", "Crew View"],
    horizontal=True,
    help="Switch between owner alerts and crew job status"
)

# Load current jobs
jobs = load_jobs()

# Calculate metrics
red_count = sum(1 for job in jobs if "🔴 HIGH RISK" in get_job_alerts(job))
orange_count = sum(1 for job in jobs if "🟠 MODERATE RISK" in get_job_alerts(job))
yellow_count = sum(1 for job in jobs if "🟡 SILENT SCOPE BLEED" in get_job_alerts(job))

# CONDITIONAL VIEW RENDERING
if view_mode == "Owner Dashboard":
    # OWNER VIEW - Original Dashboard
    # Top Metrics Row
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("🔴 HIGH RISK", red_count)
    with col2:
        st.metric("🟠 MODERATE RISK", orange_count)
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

else:
    # CREW VIEW - Mobile-First Job Cards
    st.markdown("### Active Jobs")
    
    if not jobs:
        st.info("No active jobs to display.")
    else:
        # Filter to show only jobs with remaining days > 0
        active_jobs = [j for j in jobs if j["scheduled_days_remaining"] > 0]
        
        if not active_jobs:
            st.info("All jobs completed for this week.")
        
        for job in active_jobs:
            status_label, status_color, remaining_budget = get_crew_status(job)
            tracked = get_tracked_hours(job)
            labor_target = job["labor_budget"]
            
            # Calculate minimum required
            min_required = MIN_REMAINING_LABOR_BY_TYPE.get(job["job_type"], 4)
            min_required += job["scheduled_days_remaining"] * 8
            
            # Job Card Container
            with st.container():
                st.markdown(f"""
                <div style="
                    background: white;
                    border: 1px solid #E0E0E0;
                    border-radius: 12px;
                    padding: 24px;
                    margin-bottom: 20px;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
                ">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                        <h3 style="margin: 0; font-size: 20px; font-weight: 600; color: #1a1a1a;">
                            {job['job_id']} — {job['job_type'].replace('_', ' ').title()}
                        </h3>
                        <span style="
                            background: {status_color};
                            color: white;
                            padding: 6px 14px;
                            border-radius: 20px;
                            font-size: 13px;
                            font-weight: 600;
                            letter-spacing: 0.3px;
                        ">
                            {status_label}
                        </span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Labor Target Section
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"""
                    <div style="margin-bottom: 8px;">
                        <div style="font-size: 13px; color: #757575; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;">
                            Labor Target
                        </div>
                        <div style="font-size: 28px; font-weight: 600; color: #1a1a1a;">
                            {labor_target}h
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col2:
                    st.markdown(f"""
                    <div style="margin-bottom: 8px;">
                        <div style="font-size: 13px; color: #757575; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;">
                            Hours Used
                        </div>
                        <div style="font-size: 28px; font-weight: 600; color: #1a1a1a;">
                            {tracked}h
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                
                # Progress Bar
                progress_pct = min((tracked / labor_target * 100), 100) if labor_target > 0 else 0
                st.markdown(f"""
                <div style="margin: 20px 0;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                        <span style="font-size: 13px; color: #757575;">Progress</span>
                        <span style="font-size: 13px; font-weight: 600; color: #1a1a1a;">{remaining_budget}h remaining</span>
                    </div>
                    <div style="
                        width: 100%;
                        height: 8px;
                        background: #F5F5F5;
                        border-radius: 4px;
                        overflow: hidden;
                    ">
                        <div style="
                            width: {progress_pct}%;
                            height: 100%;
                            background: {status_color};
                            transition: width 0.3s ease;
                        "></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Labor Runway Section
                runway_buffer = remaining_budget - min_required
                
                if runway_buffer >= 0:
                    runway_text = f"You have **{remaining_budget}h remaining** to complete the work below. This includes **{runway_buffer:.0f}h buffer** beyond minimum requirements."
                else:
                    runway_text = f"You have **{remaining_budget}h remaining**. Minimum work requires **{min_required}h**. Consider flagging if scope has expanded."
                
                st.markdown(f"""
                <div style="
                    background: #F8F9FA;
                    border-left: 3px solid {status_color};
                    padding: 16px;
                    border-radius: 6px;
                    margin: 20px 0;
                ">
                    <div style="font-size: 13px; font-weight: 600; color: #1a1a1a; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;">
                        Labor Runway
                    </div>
                    <div style="font-size: 15px; line-height: 1.6; color: #424242;">
                        {runway_text}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Work Remaining Section
                st.markdown("""
                <div style="font-size: 13px; font-weight: 600; color: #1a1a1a; text-transform: uppercase; letter-spacing: 0.5px; margin: 20px 0 12px 0;">
                    Work Still Required
                </div>
                """, unsafe_allow_html=True)
                
                work_items = get_minimum_remaining_work(job)
                for item in work_items:
                    st.markdown(f"""
                    <div style="
                        display: flex;
                        align-items: center;
                        padding: 10px 0;
                        border-bottom: 1px solid #F0F0F0;
                    ">
                        <span style="
                            width: 6px;
                            height: 6px;
                            background: #BDBDBD;
                            border-radius: 50%;
                            margin-right: 12px;
                        "></span>
                        <span style="font-size: 15px; color: #424242;">{item}</span>
                    </div>
                    """, unsafe_allow_html=True)
                
                st.markdown(f"""
                <div style="
                    font-size: 14px;
                    color: #757575;
                    margin-top: 12px;
                    padding-left: 18px;
                ">
                    Minimum time for above work: <strong>{min_required}h</strong>
                </div>
                """, unsafe_allow_html=True)
                
                # Flag Extra Work Button
                st.markdown("<div style='margin: 24px 0 16px 0;'>", unsafe_allow_html=True)
                
                flag_key = f"flag_extra_{job['job_id']}"
                if st.button(
                    "🚩 Flag Extra Work",
                    key=flag_key,
                    use_container_width=True,
                    help="Use this if scope has changed or additional work was requested"
                ):
                    st.info("Extra work flagged. Owner will review labor allocation.")
                
                st.markdown("</div>", unsafe_allow_html=True)
                
                # Footer Message
                st.markdown("""
                <div style="
                    margin-top: 20px;
                    padding-top: 16px;
                    border-top: 1px solid #E0E0E0;
                    font-size: 14px;
                    line-height: 1.6;
                    color: #616161;
                    text-align: center;
                ">
                    This view shows your progress toward the labor goal. Quality work matters more than speed. 
                    Flag any scope changes early so we can plan accordingly.
                </div>
                """, unsafe_allow_html=True)
                
                st.markdown("<div style='margin-bottom: 32px;'></div>", unsafe_allow_html=True)

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
**🔴 HIGH RISK**  
Remaining budget < minimum required for days left

**🟠 MODERATE RISK**  
Remaining budget < 1.25x minimum required

**🟡 SILENT SCOPE BLEED**  
Extra work flagged + extra hours > 0
""")

# Footer
st.markdown("---")
st.caption("Labor Risk Dashboard MVP | Built for painting contractors")
