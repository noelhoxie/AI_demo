"""
Generate 10 realistic automotive manufacturing equipment manuals as PDFs
and upload them to Unity Catalog Volume demo_nah_catalog.mfg_docs.manuals

Run from Databricks cluster or locally:
    pip install reportlab
    python generate_equipment_manuals.py
"""

import os
import io
import requests

# ── reportlab imports ─────────────────────────────────────────────────────────
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

W, H = A4

# ── Unity Catalog target ──────────────────────────────────────────────────────
UC_CATALOG   = os.getenv("UC_CATALOG",   "demo_nah_catalog")
UC_SCHEMA    = "mfg_docs"
UC_VOLUME    = "manuals"
DBKS_HOST    = os.getenv("DATABRICKS_HOST", "").rstrip("/")
DBKS_TOKEN   = os.getenv("DATABRICKS_TOKEN", "")
LOCAL_DIR    = "/tmp/equipment_manuals"

os.makedirs(LOCAL_DIR, exist_ok=True)

# ── Style helpers ─────────────────────────────────────────────────────────────
styles = getSampleStyleSheet()

def style(name="Normal", size=10, bold=False, color=colors.black, align=TA_LEFT, space_before=4, space_after=4):
    return ParagraphStyle(
        name, parent=styles["Normal"],
        fontSize=size, fontName="Helvetica-Bold" if bold else "Helvetica",
        textColor=color, alignment=align,
        spaceBefore=space_before, spaceAfter=space_after, leading=size * 1.4
    )

H1  = style("H1",  18, bold=True,  color=colors.HexColor("#FF3621"), space_before=12, space_after=6)
H2  = style("H2",  13, bold=True,  color=colors.HexColor("#1a1a2e"), space_before=10, space_after=4)
H3  = style("H3",  11, bold=True,  color=colors.HexColor("#2d2d44"), space_before=8,  space_after=3)
BOD = style("BOD", 10, space_before=2, space_after=2)
SML = style("SML",  9, color=colors.HexColor("#555555"), space_before=1, space_after=1)
CTR = style("CTR", 10, align=TA_CENTER)

def hr(): return HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#dddddd"), spaceAfter=6, spaceBefore=6)

def fault_table(rows):
    data = [["Fault Code", "Description", "Probable Cause", "Corrective Action"]]
    data += rows
    t = Table(data, colWidths=[2.5*cm, 5*cm, 6*cm, 6*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), colors.HexColor("#FF3621")),
        ("TEXTCOLOR",    (0,0), (-1,0), colors.white),
        ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,-1), 8),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#f9f9f9"), colors.white]),
        ("GRID",         (0,0), (-1,-1), 0.3, colors.HexColor("#cccccc")),
        ("VALIGN",       (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING",   (0,0), (-1,-1), 3),
        ("BOTTOMPADDING",(0,0), (-1,-1), 3),
    ]))
    return t

def spec_table(rows):
    t = Table(rows, colWidths=[8*cm, 11.5*cm])
    t.setStyle(TableStyle([
        ("FONTSIZE",     (0,0), (-1,-1), 9),
        ("FONTNAME",     (0,0), (0,-1), "Helvetica-Bold"),
        ("ROWBACKGROUNDS",(0,0),(-1,-1),[colors.HexColor("#f4f4f4"), colors.white]),
        ("GRID",         (0,0), (-1,-1), 0.3, colors.HexColor("#cccccc")),
        ("LEFTPADDING",  (0,0), (-1,-1), 5),
        ("TOPPADDING",   (0,0), (-1,-1), 3),
        ("BOTTOMPADDING",(0,0), (-1,-1), 3),
    ]))
    return t

def build_pdf(filename, story):
    path = os.path.join(LOCAL_DIR, filename)
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2.2*cm, bottomMargin=2*cm)
    doc.build(story)
    print(f"  Created: {path}")
    return path

# ══════════════════════════════════════════════════════════════════════════════
# Manual 1 — FANUC R-2000iC Robotic Welding System
# ══════════════════════════════════════════════════════════════════════════════
def manual_01():
    s = []
    s += [Paragraph("FANUC R-2000iC/165F Robotic Welding System", H1),
          Paragraph("Maintenance & Operations Manual  |  Rev 4.2  |  Equipment ID: BDY-WLD-01", SML), hr()]

    s += [Paragraph("1. System Overview", H2),
          Paragraph("The FANUC R-2000iC/165F is a 6-axis industrial robot with a 165 kg payload capacity configured for resistance spot welding on automotive body-in-white assemblies. The system is installed at Body Welding Station BDY-WLD-01 and performs approximately 340 welds per body assembly cycle. Operating at rated capacity the system completes a full weld cycle in 98 seconds.", BOD),
          Spacer(1, 0.3*cm)]

    s += [Paragraph("2. Technical Specifications", H2),
          spec_table([
              ["Payload Capacity", "165 kg"],
              ["Reach", "2,655 mm"],
              ["Repeatability", "±0.05 mm"],
              ["Degrees of Freedom", "6 axes (J1–J6)"],
              ["Weld Gun Type", "C-type servo gun, 8,000 N max force"],
              ["Electrode Tip Material", "Class 2 copper chromium zirconium"],
              ["Controller", "FANUC R-30iB Plus"],
              ["Power Supply", "480 VAC 3-phase, 60 Hz, 45 kVA"],
              ["Compressed Air", "0.55 MPa (80 psi), 200 L/min"],
              ["Cooling Water Flow", "12 L/min at 20°C inlet"],
          ]), Spacer(1, 0.3*cm)]

    s += [Paragraph("3. Electrode Tip Maintenance", H2),
          Paragraph("Electrode tip condition is the single most critical factor in weld quality. Worn or contaminated tips produce welds with insufficient nugget diameter, leading to pull-out failures in destructive testing.", BOD),
          Paragraph("3.1 Tip Dress Schedule", H3),
          Paragraph("Tips must be dressed every 300 welds using the automatic tip dresser. The dresser removes 0.1–0.2 mm of oxidised copper per cycle. Do not allow tips to operate beyond 400 welds without dressing as the contact face will mushroom, reducing current density below the 12 kA minimum required for class-A welds.", BOD),
          Paragraph("3.2 Tip Replacement Procedure", H3),
          Paragraph("1. Call robot to HOME position using pendant TP key F5 → POSITION → HOME.\n2. Lock out / tag out the weld gun power at CB-WLD-03 in the power panel.\n3. Allow tips to cool to below 40°C before handling (minimum 8 minutes after last weld).\n4. Use tip puller P/N 40-TIP-PULL-C2 — do not use pliers as this damages the taper seat.\n5. Inspect taper seat for burrs. Clean with copper-compatible solvent before installing new tips.\n6. Install new tips hand-tight then torque to 18 N·m using the calibrated tip torque wrench.\n7. Dress new tips 5 times before returning to production to establish flat contact faces.\n8. Log tip replacement in SAP equipment history against equipment number 10003847.", BOD),
          Spacer(1, 0.3*cm)]

    s += [Paragraph("4. Preventive Maintenance Schedule", H2),
          spec_table([
              ["Daily (each shift start)", "Inspect tip condition, check cooling water flow, verify air pressure 0.55 MPa, confirm safety light curtain response"],
              ["Weekly", "Grease J1–J3 axis gears per lubrication chart LUB-R2000-01, clean dress station, inspect cable harness routing"],
              ["Monthly", "Check all axis backlash against baseline values, inspect weld gun pivot bearing, verify force calibration on servo gun"],
              ["Quarterly", "Replace axis grease (J4–J6), inspect battery backup for encoder, perform ISO weld quality audit (10 destructive tests)"],
              ["Annual", "Full axis calibration by FANUC certified technician, replace teach pendant battery, inspect base mounting bolts 240 N·m"],
          ]), Spacer(1, 0.3*cm)]

    s += [Paragraph("5. Fault Codes and Corrective Actions", H2),
          fault_table([
              ["W-001", "Weld current low", "Worn or contaminated tips; loose secondary cable; low transformer output", "Dress or replace tips; torque secondary cable lugs to 45 N·m; check transformer tap setting"],
              ["W-007", "Tip dress overdue", "300-weld dress interval exceeded", "Run tip dress cycle immediately; check dress cycle counter in weld controller"],
              ["W-012", "Cooling water low flow", "Flow sensor fault; blocked coolant line; pump failure", "Check flow meter FT-WLD-01; flush coolant lines; inspect recirculation pump"],
              ["W-018", "Servo gun force fault", "Gun collision; servo amp alarm; force calibration drift", "Clear collision flag in R-30iB; check servo amp status; recalibrate gun force"],
              ["W-023", "Weld nugget under spec", "Tip contamination; squeeze time too short; shunt current path", "Replace tips; increase squeeze time by 2 cycles; check gun alignment to weld schedule"],
              ["W-031", "Robot position deviation", "Mechanical interference; encoder battery low; axis overload", "Check for physical obstruction; replace encoder battery if voltage < 3.0 V; reduce payload"],
              ["W-044", "Teach pendant communication fault", "Cable damage; pendant connector loose", "Inspect cable routing for pinch points; reseat pendant connector"],
          ])]

    return build_pdf("01_fanuc_r2000ic_robotic_welding.pdf", s)

# ══════════════════════════════════════════════════════════════════════════════
# Manual 2 — E-Coat Electrodeposition System
# ══════════════════════════════════════════════════════════════════════════════
def manual_02():
    s = []
    s += [Paragraph("Autophoretic E-Coat Electrodeposition System", H1),
          Paragraph("Operations & Chemistry Management Manual  |  Rev 3.1  |  Equipment ID: PNT-ECT-01", SML), hr()]

    s += [Paragraph("1. Process Overview", H2),
          Paragraph("The cathodic electrodeposition (E-Coat) system applies a corrosion-protective primer to all internal and external body surfaces through an electrically driven deposition process. The body passes through a 45,000-litre tank containing a water-borne epoxy paint emulsion at a controlled DC voltage of 260–280 V. Bath temperature is the most critical process variable — deviations of more than ±2°C from the setpoint of 27°C directly impact film build rate and cross-link density.", BOD)]

    s += [Paragraph("2. Bath Chemistry Parameters", H2),
          spec_table([
              ["Bath Temperature Setpoint", "27.0°C ± 1.5°C"],
              ["pH Range", "5.8 – 6.2"],
              ["Conductivity", "1,400 – 1,800 µS/cm"],
              ["Solids Content (NV)", "18.0 – 20.5%"],
              ["Pigment-to-Binder Ratio", "0.18 – 0.22"],
              ["MEQ Acid Value", "28 – 38 meq/100g resin"],
              ["Applied Voltage", "260 – 280 V DC"],
              ["Film Build Target", "18 – 23 µm (cured)"],
              ["Ramp Time", "30 seconds (0 to target voltage)"],
          ]), Spacer(1, 0.3*cm)]

    s += [Paragraph("3. Temperature Control Procedure", H2),
          Paragraph("Bath temperature is maintained by a plate heat exchanger in a recirculation loop. Inlet chilled water is supplied at 12°C from the central utility system.", BOD),
          Paragraph("3.1 Normal Temperature Management", H3),
          Paragraph("The bath temperature PID controller (loop TIC-ECT-01) maintains temperature within ±0.5°C under normal production. If temperature rises above 29.0°C the system automatically increases chilled water flow. If temperature exceeds 31.0°C alarm E-008 is triggered and the line should be stopped immediately — high-temperature deposition produces porous film that fails salt spray testing.", BOD),
          Paragraph("3.2 Temperature Spike Response", H3),
          Paragraph("Temperature spikes above 30°C typically result from: (a) a chilled water supply interruption, (b) bath circulation pump P-ECT-01 or P-ECT-02 running at reduced speed, or (c) high production throughput without adequate thermal recovery time. Immediately reduce throughput to 60%, increase chilled water setpoint by 3°C, and investigate the root cause before resuming full production.", BOD),
          Spacer(1, 0.3*cm)]

    s += [Paragraph("4. Filter Maintenance", H2),
          Paragraph("Ultrafiltration (UF) membranes remove paint solids from the recirculation loop. Differential pressure across the UF bank should remain below 2.8 bar. When differential pressure reaches 3.0 bar, schedule membrane cleaning within 4 hours. At 3.5 bar, stop production and clean immediately.", BOD),
          spec_table([
              ["UF membrane cleaning interval", "Every 72 hours of production (or on ΔP alarm)"],
              ["Cleaning solution", "Alkaline cleaner pH 10.5, 40°C, 30-minute soak"],
              ["Membrane replacement interval", "18 months or when clean ΔP > 1.5 bar"],
              ["Anolyte circuit flush interval", "Weekly — flush with DI water, 15 minutes"],
          ]), Spacer(1, 0.3*cm)]

    s += [Paragraph("5. Fault Codes and Corrective Actions", H2),
          fault_table([
              ["E-001", "Bath temperature high", "Chilled water flow low; heat exchanger fouled; bath circulation pump fault", "Increase chilled water flow; clean heat exchanger plates; check pump P-ECT-01 speed"],
              ["E-003", "pH out of range", "Resin addition incorrect; DI water quality degraded", "Add neutralising amine solution 0.5 L increments; check DI water conductivity < 5 µS/cm"],
              ["E-008", "Temperature critical — stop line", "Bath temp above 31°C", "Stop production immediately; call process engineer; increase chilled water; log in SAP QM"],
              ["E-011", "UF differential pressure high", "Membranes fouled; feed pump restricted", "Initiate CIP clean cycle; check P-UF-01 discharge pressure"],
              ["E-015", "Rectifier voltage out of range", "Rectifier fault; electrode connection loose; bath conductivity low", "Check rectifier status panel; inspect anode connections; measure bath conductivity"],
              ["E-019", "Circulation pump fault", "Motor overload; impeller cavitation; shaft seal leak", "Check motor current at MCC-PAINT-02; inspect for cavitation noise; check seal gland"],
              ["E-024", "Film build under target", "Bath temperature low; voltage too low; body not fully immersed; contact resistance high", "Review TIC-ECT-01; check voltage ramp profile; verify conveyor immersion depth"],
          ])]

    return build_pdf("02_ecoat_electrodeposition_system.pdf", s)

# ══════════════════════════════════════════════════════════════════════════════
# Manual 3 — 800-Ton Progressive Die Stamping Press
# ══════════════════════════════════════════════════════════════════════════════
def manual_03():
    s = []
    s += [Paragraph("800-Ton Progressive Die Stamping Press", H1),
          Paragraph("Safety, Setup & Maintenance Manual  |  Rev 2.8  |  Equipment ID: BDY-STM-01", SML), hr()]

    s += [Paragraph("1. Safety Requirements", H2),
          Paragraph("CRITICAL: The stamping press develops 800 metric tons of closing force. All work within the die space requires a physical die block to be installed AND the main drive disconnected at the motor control centre before any personnel entry. Never rely on the brake alone as the sole means of preventing ram descent.", BOD),
          Spacer(1, 0.3*cm)]

    s += [Paragraph("2. Technical Specifications", H2),
          spec_table([
              ["Press Tonnage", "800 metric tons"],
              ["Stroke Length", "300 mm"],
              ["Strokes Per Minute", "8–18 SPM (variable)"],
              ["Die Space (height)", "900 mm"],
              ["Bed Size", "3,600 × 1,800 mm"],
              ["Feed Direction", "Right to left"],
              ["Coil Width Capacity", "Up to 1,400 mm"],
              ["Strip Thickness Range", "0.65 – 2.5 mm"],
              ["Lubrication System", "Centralised automatic die lube, 20 L reservoir"],
              ["Air Counterbalance Pressure", "4.5 – 5.2 MPa (set per die weight)"],
          ]), Spacer(1, 0.3*cm)]

    s += [Paragraph("3. Die Lubrication System", H2),
          Paragraph("The centralised die lubrication system delivers coolant-lubricant to 24 die spray nozzles on a programmable cycle timed to the press stroke. Inadequate lubrication is the primary cause of premature die wear and part dimensional drift.", BOD),
          Paragraph("3.1 Lubricant Pressure Specification", H3),
          Paragraph("System pressure must be maintained between 2.8 and 4.2 bar at the manifold. Pressure below 2.0 bar triggers fault code S-009 and will inhibit the press from running. Check the reservoir level (minimum 6 litres), inspect filter element (replace if ΔP > 0.8 bar), and verify pump P-LUB-01 is running when alarm S-009 is active.", BOD),
          Paragraph("3.2 Nozzle Inspection", H3),
          Paragraph("Inspect all 24 nozzles at each die change. Clogged nozzles should be removed, soaked in mineral spirits for 10 minutes, and blown clear with compressed air. Replace nozzles that show cracking or deformation.", BOD),
          Spacer(1, 0.3*cm)]

    s += [Paragraph("4. Counterbalance Pressure Setup", H2),
          Paragraph("Air counterbalance pressure must be set to match the die weight to ensure smooth ram reversal and prevent upper die bounce. Use the following reference settings:", BOD),
          spec_table([
              ["Die weight 800–1,200 kg",  "4.5 MPa"],
              ["Die weight 1,200–1,800 kg", "4.8 MPa"],
              ["Die weight 1,800–2,400 kg", "5.0 MPa"],
              ["Die weight > 2,400 kg",    "5.2 MPa"],
          ]), Spacer(1, 0.3*cm)]

    s += [Paragraph("5. Fault Codes and Corrective Actions", H2),
          fault_table([
              ["S-001", "Brake wear limit reached", "Excessive brake actuations; contaminated brake pads", "Replace brake pads; measure braking distance must be < 12 mm at 18 SPM"],
              ["S-005", "Feed length error", "Strip buckling; pilot pin wear; feed clamp pressure low", "Check pilot pin clearance; adjust feed clamp to 0.55 MPa; inspect coil edge condition"],
              ["S-009", "Die lube pressure low", "Reservoir empty; filter blocked; pump P-LUB-01 fault", "Fill reservoir; replace filter element; check pump motor at MCC-STAMP-01"],
              ["S-013", "Overload protection tripped", "Die crash; foreign material; strip double-feed", "Clear die space; inspect for die damage; check strip guide alignment"],
              ["S-017", "Light curtain fault", "Object in curtain beam; sensor misalignment; dirty lens", "Clear curtain area; realign sender/receiver; clean lenses with IPA"],
              ["S-022", "Encoder position fault", "Encoder cable damage; encoder wheel debris", "Clean encoder wheel; inspect cable; replace encoder if signal intermittent"],
          ])]

    return build_pdf("03_stamping_press_800ton.pdf", s)

# ══════════════════════════════════════════════════════════════════════════════
# Manual 4 — Transfer Car Final Assembly System
# ══════════════════════════════════════════════════════════════════════════════
def manual_04():
    s = []
    s += [Paragraph("Transfer Car Final Assembly System", H1),
          Paragraph("Technical & Troubleshooting Manual  |  Rev 5.0  |  Equipment ID: FAL-ASM-01", SML), hr()]

    s += [Paragraph("1. System Description", H2),
          Paragraph("The Final Assembly Line transfer car system transports vehicle bodies through 18 assembly stations using 4 independently driven transfer cars on a closed-loop rail circuit. The system converges output from Body Shop (Line A), Paint Shop (Line B), and Powertrain (Line C). A single fault at FAL-ASM-01 blocks all three upstream lines simultaneously as WIP queues at each line's end station.", BOD),
          Spacer(1, 0.3*cm)]

    s += [Paragraph("2. Transfer Car Specifications", H2),
          spec_table([
              ["Number of Cars",             "4 (TC1 – TC4)"],
              ["Car Capacity",               "800 kg (body + fixtures)"],
              ["Travel Speed",               "12 m/min (normal); 6 m/min (approach)"],
              ["Position Accuracy",          "±1.5 mm at station stops"],
              ["Drive System",               "AC servo motor, 7.5 kW per car"],
              ["Position Feedback",          "Absolute encoder, 2048 ppr — P/N TC4-ENC-200"],
              ["PLC Controller",             "Siemens S7-1500 PN"],
              ["Communication Protocol",     "PROFINET, 100 Mbit"],
              ["Emergency Stop Category",    "Category 3, PLd per ISO 13849"],
              ["Lubrication",                "Automatic rail lubrication every 8 operating hours"],
          ]), Spacer(1, 0.3*cm)]

    s += [Paragraph("3. Encoder Replacement Procedure (Fault E-047)", H2),
          Paragraph("Fault E-047 indicates that the absolute encoder on Transfer Car 4 (TC4) has lost position reference. This is the most common critical fault on FAL-ASM-01 and accounts for 68% of all line stoppages. The encoder P/N TC4-ENC-200 has a rated service life of 12,000 operating hours under normal conditions.", BOD),
          Paragraph("3.1 Diagnosis", H3),
          Paragraph("Before replacing the encoder, confirm the fault is genuine rather than a wiring or connector issue:\n1. Open the TC4 junction box (J-TC4-01) and check connector X14 is fully seated.\n2. Measure encoder supply voltage at X14 pins 1(+5V) and 2(GND) — must read 4.9–5.1 V.\n3. Monitor encoder output on PROFINET diagnostic screen: if position value is frozen or increments incorrectly during manual jog, the encoder is faulty.\n4. Check for condensation inside the encoder housing — this is common after weekend plant shutdowns.", BOD),
          Paragraph("3.2 Replacement Steps", H3),
          Paragraph("1. Stop the transfer car system using HMI Emergency Stop button ES-FAL-01.\n2. Lock out / tag out power at MCC-FAL-01 panel, circuit breaker CB-TC4-DRV.\n3. Manually drive TC4 to the maintenance bay using battery backup pendant.\n4. Record the current absolute position displayed on S7-1500 screen (Data Block DB_TC4, address 0.0) before disconnecting power — required for post-installation homing.\n5. Remove the encoder cover (4× M5 bolts). Photograph encoder cable routing before disconnection.\n6. Disconnect the M12 connector on encoder cable EC-TC4-001.\n7. Remove encoder mounting bolts (3× M6, 8 N·m torque). Slide encoder off shaft — do not use a lever as this damages the shaft.\n8. Install new encoder P/N TC4-ENC-200. Align coupling to within 0.1 mm axial runout using a dial indicator.\n9. Torque mounting bolts to 8 N·m in a star pattern.\n10. Reconnect M12 connector. Verify pinout: Pin 1 = +5 V, Pin 2 = GND, Pin 3 = CLK+, Pin 4 = CLK−, Pin 5 = DATA+, Pin 6 = DATA−.\n11. Restore power. On S7-1500 HMI navigate to TC4 → HOMING → EXECUTE HOMING SEQUENCE.\n12. Verify TC4 moves to station 1 reference point and position reads 0.000.\n13. Perform 3 complete circuit runs in manual mode before returning to automatic production.\n14. Log encoder replacement in SAP maintenance order against equipment 10003847.", BOD),
          Spacer(1, 0.3*cm)]

    s += [Paragraph("4. PLC Sequence Reset After Fault", H2),
          Paragraph("After clearing any E-0xx fault, the PLC sequence must be reset before automatic mode can be re-enabled:\n1. On the HMI, navigate to DIAGNOSTICS → FAULT LOG and acknowledge all active alarms.\n2. Press RESET SEQUENCE on the main transfer car control screen.\n3. Confirm all 4 cars report READY status (green indicator).\n4. Press AUTO MODE ENABLE — the system will perform a self-check before accepting production commands.\n5. Notify upstream line supervisors that FAL-ASM-01 is ready to accept WIP.", BOD),
          Spacer(1, 0.3*cm)]

    s += [Paragraph("5. Fault Codes and Corrective Actions", H2),
          fault_table([
              ["E-001", "Car 1 position fault", "Encoder signal loss; rail debris at position sensor", "Check encoder cable; clean position sensor lens; re-home TC1"],
              ["E-012", "Conveyor drive overload", "Car loaded above 800 kg; rail obstruction; motor fault", "Check car load; inspect rail for debris; check motor thermal at MCC-FAL-01"],
              ["E-031", "PROFINET communication fault", "Network cable damage; switch fault; PLC module error", "Check cable TC4-PN-001; restart managed switch SW-FAL-03; check PLC module status"],
              ["E-047", "TC4 encoder position lost", "Encoder P/N TC4-ENC-200 failed; cable connector loose; condensation in housing", "Replace encoder per section 3.2; check M12 connector X14; verify +5 V supply"],
              ["E-052", "Emergency stop activated", "E-stop button pressed; safety circuit open", "Identify and clear E-stop cause; acknowledge alarm; perform sequence reset per section 4"],
              ["E-058", "Rail lubrication fault", "Lubricator pump empty; blocked nozzle", "Refill lubricator reservoir; clean nozzles; verify pump output 3 mL per cycle"],
          ])]

    return build_pdf("04_transfer_car_assembly_system.pdf", s)

# ══════════════════════════════════════════════════════════════════════════════
# Manual 5 — CNC Horizontal Machining Centre
# ══════════════════════════════════════════════════════════════════════════════
def manual_05():
    s = []
    s += [Paragraph("CNC Horizontal Machining Centre — Block & Head Line", H1),
          Paragraph("Operator & Maintenance Manual  |  Rev 2.3  |  Equipment ID: PTN-MCH-01", SML), hr()]

    s += [Paragraph("1. Machine Overview", H2),
          Paragraph("The CNC horizontal machining centre at station PTN-MCH-01 performs precision boring, milling, and drilling operations on engine cylinder block castings. The machine features a 50-taper spindle capable of 6,000 RPM and a 60-position tool magazine. Coolant is delivered through the spindle at up to 70 bar for deep-hole operations.", BOD)]

    s += [Paragraph("2. Oil Pressure System", H2),
          Paragraph("Hydraulic and lubrication oil is circulated by pump P-MCH-01 (7.5 kW, 25 L/min at 4.5 bar). Minimum operating pressure is 2.5 bar — below this threshold the spindle clamping system cannot maintain adequate tool retention force and production must stop.", BOD),
          Paragraph("2.1 Low Oil Pressure Response", H3),
          Paragraph("Fault M-019 (Oil Pressure Low) is triggered when measured pressure falls below 2.5 bar for more than 3 seconds. Immediate response:\n1. Stop the spindle and retract the tool to a safe position.\n2. Check oil level in the central hydraulic unit tank — minimum mark is 45 litres.\n3. Inspect inline filter element P/N HYD-FILT-50µ — replace if ΔP indicator shows red.\n4. Check pump P-MCH-01 outlet pressure at gauge G-MCH-HYD-01.\n5. Inspect pressure relief valve PRV-MCH-01 setting — should be 5.0 bar, not below 4.5 bar.\nIf pressure does not recover after the above checks, call the hydraulics specialist — do not restart the spindle with oil pressure below specification.", BOD),
          Spacer(1, 0.3*cm)]

    s += [Paragraph("3. Spindle Maintenance", H2),
          spec_table([
              ["Spindle bearing lubrication", "Oil-air lubrication, 0.2 mL per hour — check reservoir weekly"],
              ["Spindle thermal compensation", "Active — do not disable; warm-up cycle required after cold start (15 min)"],
              ["Tool retention force", "Minimum 16,000 N — test monthly with retention force gauge"],
              ["Spindle runout", "Maximum 2 µm TIR at gauge line — check after any spindle crash"],
              ["Coolant-through-spindle pressure", "70 bar maximum; check rotary union seal quarterly for leakage"],
          ]), Spacer(1, 0.3*cm)]

    s += [Paragraph("4. Fault Codes and Corrective Actions", H2),
          fault_table([
              ["M-004", "Tool magazine jam", "Tool retention finger damaged; chip accumulation in magazine", "Clear magazine manually; inspect retention fingers; clean magazine with air blast"],
              ["M-011", "Spindle overload", "Tool wear excessive; incorrect cutting parameters; chip evacuation blocked", "Replace tool; verify spindle load in NC program against max 85% for sustained cuts"],
              ["M-019", "Oil pressure low", "Filter blocked; oil level low; pump P-MCH-01 worn; PRV set too low", "Follow section 2.1 low pressure response procedure"],
              ["M-027", "Coolant pressure fault", "Coolant pump fault; filter blocked; coolant level low", "Check pump CP-MCH-01; replace coolant filter; top up coolant tank to 80% mark"],
              ["M-034", "Axis position error", "Servo fault; mechanical interference; ball screw backlash", "Check servo alarm on drive; clear interference; measure ball screw backlash"],
          ])]

    return build_pdf("05_cnc_machining_centre.pdf", s)

# ══════════════════════════════════════════════════════════════════════════════
# Manual 6 — Body Side Panel Sealing System
# ══════════════════════════════════════════════════════════════════════════════
def manual_06():
    s = []
    s += [Paragraph("Automated Body Side Panel Sealing System", H1),
          Paragraph("Operations & Nozzle Maintenance Manual  |  Rev 1.9  |  Equipment ID: BDY-SLD-01", SML), hr()]

    s += [Paragraph("1. System Overview", H2),
          Paragraph("The body sealing system applies PVC-based seam sealant to 14 seam locations on each body assembly to prevent water ingress, corrosion, and road noise transmission. Two 6-axis robots (SEAL-R1 and SEAL-R2) equipped with sealant applicator guns deliver a 8 mm ± 1 mm bead width. Bead quality is verified by a laser profilometer mounted on each robot wrist.", BOD)]

    s += [Paragraph("2. Sealant Application Parameters", H2),
          spec_table([
              ["Sealant Material",        "PVC-based body sealer, viscosity 80,000–120,000 mPa·s at 23°C"],
              ["Application Temperature", "23°C ± 2°C (material must be conditioned 12 hours before use)"],
              ["System Pressure",         "180–220 bar (gear pump output)"],
              ["Application Speed",       "300 mm/s ± 20 mm/s"],
              ["Bead Width Target",       "8 mm ± 1 mm"],
              ["Bead Height Target",      "4 mm ± 0.5 mm"],
              ["Nozzle Tip Size",         "3.5 mm round orifice"],
              ["Flush Interval",          "Every 4 hours or at material changeover"],
          ]), Spacer(1, 0.3*cm)]

    s += [Paragraph("3. Nozzle Maintenance", H2),
          Paragraph("Nozzle blockage and wear are the primary causes of bead geometry faults. The nozzle assembly must be cleaned every 4 hours during production and fully replaced every 500 operating hours.", BOD),
          Paragraph("3.1 Nozzle Cleaning Procedure", H3),
          Paragraph("1. Command robot to CLEAN POSITION using HMI → ROBOT → MANUAL → CLEAN POS.\n2. Relieve system pressure using the pump dump valve DV-SEAL-01.\n3. Remove nozzle tip with the 22 mm open-end spanner (do not use adjustable wrench — damages hex flats).\n4. Soak nozzle in PVC sealant solvent for 5 minutes.\n5. Clear orifice with a 3.0 mm brass cleaning pin — never use steel as this scratches the orifice bore.\n6. Blow clear with dry compressed air at 4 bar.\n7. Reinstall and torque to 25 N·m.\n8. Run a 200 mm test bead on the calibration plate and measure with the laser profilometer.", BOD),
          Spacer(1, 0.3*cm)]

    s += [Paragraph("4. Cycle Time Deviation Monitoring", H2),
          Paragraph("Normal cycle time for the sealing operation is 48 ± 3 seconds. Cycle times exceeding 55 seconds indicate: sealant pump cavitation, material viscosity out of range (check material temperature), robot path deviation (check TCP calibration), or nozzle partial blockage reducing flow rate. Fault B-018 is raised when cycle time deviation exceeds 15% of the 48-second baseline.", BOD),
          Spacer(1, 0.3*cm)]

    s += [Paragraph("5. Fault Codes and Corrective Actions", H2),
          fault_table([
              ["B-003", "Bead width under spec", "Nozzle blocked; material pressure low; material viscosity high", "Clean nozzle; check system pressure 180–220 bar; verify material temperature 23°C ± 2°C"],
              ["B-009", "Laser profilometer fault", "Lens contaminated; calibration drift; cable damage", "Clean lens with IPA; run profilometer calibration cycle; check cable routing"],
              ["B-014", "Gear pump pressure low", "Material reservoir empty; pump wear; inlet filter blocked", "Refill material drum; check pump output pressure; replace inlet filter"],
              ["B-018", "Cycle time deviation", "See section 4 for causes", "Follow section 4 diagnostic procedure; check material conditioning temperature"],
              ["B-022", "Material temperature out of range", "Conditioning room temperature change; heater fault in supply line", "Return material to conditioning room; check line heater HT-SEAL-01"],
          ])]

    return build_pdf("06_body_sealing_system.pdf", s)

# ══════════════════════════════════════════════════════════════════════════════
# Manual 7 — Electrostatic Base Coat Application Robot
# ══════════════════════════════════════════════════════════════════════════════
def manual_07():
    s = []
    s += [Paragraph("Electrostatic Base Coat Application Robot", H1),
          Paragraph("Operations & Atomizer Maintenance Manual  |  Rev 3.3  |  Equipment ID: PNT-BSC-01", SML), hr()]

    s += [Paragraph("1. Safety — High Voltage", H2),
          Paragraph("DANGER: The electrostatic system operates at up to 90,000 V DC. All personnel must stay outside the safety fence (marked in yellow) when the high voltage is energised. The interlock system disconnects high voltage when any fence gate is opened, but never assume the system is de-energised without confirming the HV indicator lamp is extinguished and measuring with an approved HV probe.", BOD)]

    s += [Paragraph("2. Rotary Atomizer Specifications", H2),
          spec_table([
              ["Atomizer type",              "High-speed rotary bell, air-driven turbine"],
              ["Bell speed range",           "15,000 – 60,000 RPM"],
              ["Bell speed at production",   "40,000 – 45,000 RPM (colour-dependent)"],
              ["Electrostatic voltage",      "70,000 – 90,000 V DC (negative)"],
              ["Shaping air pressure",       "1.0 – 2.5 bar (controls fan pattern width)"],
              ["Paint flow rate",            "200 – 450 mL/min"],
              ["Solvent flush volume",       "80 mL per colour change"],
              ["Turbine air supply",         "Clean dry air, dew point < −40°C, 6 bar"],
          ]), Spacer(1, 0.3*cm)]

    s += [Paragraph("3. Atomizer Cleaning", H2),
          Paragraph("The bell cup must be cleaned every 8 hours of production or at every colour change to prevent paint buildup that causes imbalance and premature bearing failure.", BOD),
          Paragraph("3.1 Automatic Colour Change Flush Sequence", H3),
          Paragraph("The automatic colour change sequence takes 42 seconds and delivers 80 mL of solvent through the atomizer followed by 20 mL of new colour to purge the lines. Verify colour change completion by inspecting the colour sensor reading on the HMI — target dE < 1.0 before the body enters the booth.", BOD),
          Paragraph("3.2 Manual Bell Cup Removal and Cleaning", H3),
          Paragraph("1. Select HMI → MAINTENANCE → ATOMIZER OFF → confirm HV lamp extinguished.\n2. Wait 60 seconds for turbine to decelerate to 0 RPM (confirm on RPM display).\n3. Place a collection tray under the atomizer.\n4. Use bell cup removal tool P/N ATZ-REMOVE-07 — turn counterclockwise 90° then pull straight.\n5. Soak bell cup in solvent bath for 10 minutes.\n6. Clean with soft-bristle brush — never use abrasives.\n7. Inspect bell cup edge for nicks or runout > 0.03 mm TIR — replace if damaged.\n8. Reinstall bell cup and torque to 12 N·m.", BOD),
          Spacer(1, 0.3*cm)]

    s += [Paragraph("4. Fault Codes and Corrective Actions", H2),
          fault_table([
              ["P-002", "HV current leakage high", "Paint on HV components; humidity in booth > 85%; insulator contaminated", "Clean HV components with IPA; check booth humidity; clean insulators"],
              ["P-008", "Bell speed deviation", "Turbine air supply pressure low; bearing wear; bell cup imbalance", "Check turbine air at 6 bar; measure bearing temperature; inspect bell cup balance"],
              ["P-015", "Colour sensor fault", "Sensor lens dirty; fibre cable damaged", "Clean sensor lens; inspect fibre cable; recalibrate colour sensor"],
              ["P-021", "Paint flow fault", "Colour change valve stuck; paint filter blocked; flow meter fault", "Cycle colour change valve; replace paint filter element; check flow meter FT-BSC-01"],
              ["P-028", "Spray pattern deviation", "Shaping air pressure incorrect; bell cup worn; paint viscosity out of range", "Adjust shaping air per colour card; replace bell cup; check paint viscosity 18–22 s DIN4"],
          ])]

    return build_pdf("07_basecoat_application_robot.pdf", s)

# ══════════════════════════════════════════════════════════════════════════════
# Manual 8 — Engine Dynamometer Test System
# ══════════════════════════════════════════════════════════════════════════════
def manual_08():
    s = []
    s += [Paragraph("Engine Dynamometer Test System", H1),
          Paragraph("Calibration & Safety Manual  |  Rev 1.7  |  Equipment ID: PTN-DYN-01", SML), hr()]

    s += [Paragraph("1. System Description", H2),
          Paragraph("The engine dynamometer at station PTN-DYN-01 performs end-of-line acceptance testing on all assembled powertrain modules before shipment to the final assembly line. Each engine undergoes a 12-minute warm-up and test cycle measuring power output, torque curve, idle stability, and oil consumption rate.", BOD)]

    s += [Paragraph("2. Coupling and Vibration", H2),
          Paragraph("The flexible jaw coupling connecting the engine output shaft to the dynamometer absorbs torsional shock and misalignment. Coupling wear produces characteristic vibration signatures that are detected by the vibration sensor VS-DYN-01 mounted on the dynamometer bearing housing.", BOD),
          Paragraph("2.1 Vibration Alarm Thresholds", H3),
          spec_table([
              ["Normal operation",     "< 2.0 mm/s RMS (10–1,000 Hz)"],
              ["Advisory level",       "2.0 – 3.5 mm/s RMS — schedule inspection at next window"],
              ["Warning level",        "3.5 – 5.0 mm/s RMS — complete current test cycle then stop"],
              ["Danger level",         "> 5.0 mm/s RMS — stop immediately, do not restart until inspected"],
          ]),
          Paragraph("Vibration above 3.5 mm/s RMS is most commonly caused by: (a) coupling jaw insert wear — inserts should be replaced every 60,000 engine test cycles, (b) coupling misalignment greater than 0.15 mm parallel or 0.05° angular, or (c) engine assembly imbalance indicating a production defect.", BOD),
          Spacer(1, 0.3*cm)]

    s += [Paragraph("3. Load Cell Calibration", H2),
          Paragraph("The torque measurement load cell must be calibrated every 30 days using a certified deadweight calibration arm. Calibration drift of more than 0.5% requires immediate recalibration before further production testing.", BOD),
          spec_table([
              ["Calibration interval",     "30 days or after any mechanical shock event"],
              ["Calibration arm length",   "1,000 mm ± 0.1 mm (traceable to NIST)"],
              ["Calibration weights",      "50 kg, 100 kg (certified to 0.02% accuracy)"],
              ["Acceptable zero drift",    "< 0.1% full scale (500 N·m)"],
              ["Acceptable span drift",    "< 0.5% full scale"],
          ]), Spacer(1, 0.3*cm)]

    s += [Paragraph("4. Fault Codes and Corrective Actions", H2),
          fault_table([
              ["D-003", "Vibration warning", "Coupling insert worn; misalignment; engine imbalance", "Replace coupling inserts P/N DYN-JAW-INSERT; check alignment; inspect engine assembly"],
              ["D-009", "Load cell overrange", "Engine torque spike; mechanical shock to load cell", "Inspect load cell for damage; recalibrate before resuming testing"],
              ["D-014", "Exhaust temperature high", "Rich fuel mixture; oil consumption high; catalyst fault", "Inspect fuel injectors; check piston ring seal; notify engine assembly QC"],
              ["D-019", "Coolant flow low to dynamometer", "Coolant pump fault; blocked circuit; temperature control valve stuck", "Check pump P-DYN-CLT; flush circuit; inspect TCV-DYN-01 position"],
              ["D-024", "Speed control instability", "Servo drive fault; coupling backlash; engine idle fault", "Check dynamometer servo drive; measure coupling backlash; review engine test data"],
          ])]

    return build_pdf("08_engine_dynamometer_system.pdf", s)

# ══════════════════════════════════════════════════════════════════════════════
# Manual 9 — Chain-on-Edge Conveyor System
# ══════════════════════════════════════════════════════════════════════════════
def manual_09():
    s = []
    s += [Paragraph("Chain-on-Edge Overhead Conveyor System", H1),
          Paragraph("Installation, Maintenance & Troubleshooting  |  Rev 2.1  |  Equipment ID: BDY-INS-01", SML), hr()]

    s += [Paragraph("1. System Overview", H2),
          Paragraph("The chain-on-edge overhead conveyor transports body assemblies through inspection, sealing, and pre-treatment zones at a variable speed of 2.5–6 m/min. The conveyor uses a 160 mm pitch forged steel chain with encoded trolleys for body tracking. Total chain length is 480 metres with a nominal chain tension of 12,000 N.", BOD)]

    s += [Paragraph("2. Chain Tension Adjustment", H2),
          Paragraph("Correct chain tension is critical for smooth travel and long chain life. Insufficient tension causes chain sag and skipping at drive sprockets; excessive tension accelerates bearing wear on trolleys and the drive unit.", BOD),
          spec_table([
              ["Normal operating tension",  "10,000 – 14,000 N (measured at tensioner take-up)"],
              ["Tensioner travel range",    "600 mm total; 300 mm normal operating range"],
              ["Take-up adjustment",        "20 N·m on each tensioner bolt — 1 full turn = 6 mm of chain take-up"],
              ["Chain elongation limit",    "Replace when measured pitch exceeds 162 mm (1.25% elongation)"],
              ["Lubrication",               "Automatic chain oiler at drive unit; verify 1 drop per link per 8 hours"],
          ]), Spacer(1, 0.3*cm)]

    s += [Paragraph("3. Drive Motor and Gearbox Maintenance", H2),
          spec_table([
              ["Drive motor",               "15 kW, 1,460 RPM, IE3 efficiency class"],
              ["Gearbox ratio",             "40:1 helical bevel gearbox"],
              ["Gearbox oil grade",         "ISO VG 220 synthetic gear oil"],
              ["Gearbox oil change interval","5,000 operating hours or annually"],
              ["Motor bearing grease",      "2 grams per bearing every 3,000 hours"],
              ["Drive sprocket tooth wear", "Replace when tooth profile exceeds 3 mm wear depth"],
          ]), Spacer(1, 0.3*cm)]

    s += [Paragraph("4. Fault Codes and Corrective Actions", H2),
          fault_table([
              ["C-002", "Drive motor overload", "Chain tension excessive; foreign body in conveyor; overloaded body fixtures", "Check take-up tension; inspect full conveyor length for obstruction; check fixture weight"],
              ["C-007", "Chain speed deviation", "Speed encoder fault; drive belt slip; motor speed controller fault", "Check encoder signal; inspect drive belt tension; check VFD output frequency"],
              ["C-015", "Body tracking lost", "RFID tag missing on trolley; reader antenna fault; tag damaged", "Replace RFID tag on affected trolley; clean reader antenna; check reader power supply"],
              ["C-021", "Chain lubrication fault", "Oil reservoir empty; oiler nozzle blocked; solenoid valve fault", "Fill oil reservoir; clean nozzle with solvent; check solenoid valve SV-CLB-01"],
              ["C-028", "Chain tension alarm", "Take-up at limit; chain elongated beyond limit; counterweight stuck", "Check take-up position; measure chain pitch; free counterweight if jammed"],
          ])]

    return build_pdf("09_chain_conveyor_system.pdf", s)

# ══════════════════════════════════════════════════════════════════════════════
# Manual 10 — Automated Vision Inspection System
# ══════════════════════════════════════════════════════════════════════════════
def manual_10():
    s = []
    s += [Paragraph("Automated Vision Inspection System", H1),
          Paragraph("Camera Calibration & Operations Manual  |  Rev 2.5  |  Equipment ID: PNT-INS-01", SML), hr()]

    s += [Paragraph("1. System Overview", H2),
          Paragraph("The automated vision inspection system uses 12 high-resolution cameras (5 megapixel, 100 mm telecentric lenses) mounted in a tunnel configuration to inspect painted body surfaces for defects including blistering, pinholes, cratering, sagging, and colour deviation. The system runs on a Databricks-connected inference pipeline using a convolutional neural network trained on 85,000 labelled panel images.", BOD)]

    s += [Paragraph("2. Camera Calibration Procedure", H2),
          Paragraph("Cameras must be calibrated every 7 days or whenever the wavescan inspection score deviates more than 3 points from the certified body standard. Calibration requires the calibration target body (stored in the maintenance bay, identified by a blue label).", BOD),
          Paragraph("2.1 White Balance and Exposure Calibration", H3),
          Paragraph("1. Run the calibration body through the tunnel at normal production speed.\n2. Open the Vision Manager software and navigate to CALIBRATION → AUTO WHITE BALANCE.\n3. Click CAPTURE CALIBRATION FRAME — the system acquires 48 images (4 per camera × 12 cameras).\n4. Verify that all 12 cameras show an exposure histogram peak between 120 and 200 DN (8-bit scale).\n5. If any camera shows clipping (pixels at 255) or underexposure (peak below 80 DN), adjust the LED intensity for that camera zone using the lighting controller LCS-INS-01.\n6. Click APPLY AND SAVE. Back up the calibration file to the network share \\\\mfg-server\\vision-backup.", BOD),
          Paragraph("2.2 Geometric Calibration (Monthly)", H3),
          Paragraph("Mount the 3D calibration target plate on the conveyor fixture and run it through the tunnel. The software calculates lens distortion coefficients and corrects the camera matrices. This procedure takes 8 minutes. Do not adjust camera positions after geometric calibration without repeating this procedure.", BOD),
          Spacer(1, 0.3*cm)]

    s += [Paragraph("3. Defect Classification Thresholds", H2),
          spec_table([
              ["Pinhole defect",       "Minimum detectable diameter: 0.3 mm; reject threshold: any pinhole > 0.5 mm in class-A zone"],
              ["Blistering",           "Reject if total affected area > 4 cm² or any single blister > 8 mm diameter"],
              ["Cratering",            "Reject if crater depth > 15 µm (measured by profilometry integration)"],
              ["Sagging",              "Reject if sag height > 1.2 mm over any 50 mm length"],
              ["Colour deviation",     "Reject if dE > 1.5 CIE2000 against master colour standard"],
              ["Dirt inclusion",       "Reject if particle > 0.8 mm in class-A zone or > 1.5 mm elsewhere"],
          ]), Spacer(1, 0.3*cm)]

    s += [Paragraph("4. Fault Codes and Corrective Actions", H2),
          fault_table([
              ["V-003", "Camera offline", "Power supply fault; cable damage; camera firmware crash", "Check 24V supply at camera hub CH-INS-01; inspect cable; power cycle camera via web interface"],
              ["V-008", "Lighting intensity low", "LED array degradation; driver fault; filter contaminated", "Measure LED output at current level; replace driver module LED-DRV-0x; clean diffuser panel"],
              ["V-012", "Calibration drift alarm", "Thermal shift; vibration; camera moved", "Re-run calibration per section 2; check camera mounting bolts 6 N·m"],
              ["V-017", "False reject rate high", "Calibration needed; model confidence threshold too tight; surface contamination on calibration body", "Run calibration; adjust threshold from 0.85 to 0.80 in config; clean calibration body"],
              ["V-021", "Image processing timeout", "GPU overload; network latency; storage I/O bottleneck", "Check GPU utilisation < 85%; verify network throughput; check SSD write speed on inference server"],
          ])]

    return build_pdf("10_vision_inspection_system.pdf", s)


# ══════════════════════════════════════════════════════════════════════════════
# Upload to Unity Catalog Volume
# ══════════════════════════════════════════════════════════════════════════════
def upload_to_uc(local_path, filename):
    """Upload a file to Unity Catalog Volume using the Databricks Files API."""
    if not DBKS_HOST or not DBKS_TOKEN:
        print(f"  Skipping UC upload (no credentials configured): {filename}")
        return
    uc_path = f"/Volumes/{UC_CATALOG}/{UC_SCHEMA}/{UC_VOLUME}/{filename}"
    url = f"{DBKS_HOST}/api/2.0/fs/files{uc_path}"
    with open(local_path, "rb") as f:
        resp = requests.put(url,
            headers={"Authorization": f"Bearer {DBKS_TOKEN}"},
            data=f,
            params={"overwrite": "true"}
        )
    if resp.status_code in (200, 204):
        print(f"  Uploaded to UC: {uc_path}")
    else:
        print(f"  Upload failed ({resp.status_code}): {resp.text[:200]}")


def ensure_uc_volume():
    """Create schema and volume in Unity Catalog if they don't exist."""
    if not DBKS_HOST or not DBKS_TOKEN:
        return
    host, hdrs = DBKS_HOST, {"Authorization": f"Bearer {DBKS_TOKEN}", "Content-Type": "application/json"}
    # Create schema
    r = requests.post(f"{DBKS_HOST}/api/2.1/unity-catalog/schemas",
                      headers=hdrs,
                      json={"name": UC_SCHEMA, "catalog_name": UC_CATALOG})
    if r.status_code not in (200, 409):
        print(f"  Schema creation warning: {r.status_code}")
    # Create volume
    r = requests.post(f"{DBKS_HOST}/api/2.1/unity-catalog/volumes",
                      headers=hdrs,
                      json={"name": UC_VOLUME, "catalog_name": UC_CATALOG,
                            "schema_name": UC_SCHEMA, "volume_type": "MANAGED"})
    if r.status_code not in (200, 409):
        print(f"  Volume creation warning: {r.status_code}")
    else:
        print(f"  UC Volume ready: /Volumes/{UC_CATALOG}/{UC_SCHEMA}/{UC_VOLUME}")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Generating equipment manuals...")
    ensure_uc_volume()
    generators = [manual_01, manual_02, manual_03, manual_04, manual_05,
                  manual_06, manual_07, manual_08, manual_09, manual_10]
    for gen in generators:
        path = gen()
        upload_to_uc(path, os.path.basename(path))
    print(f"\nDone. PDFs saved to: {LOCAL_DIR}")
    print(f"Unity Catalog Volume: /Volumes/{UC_CATALOG}/{UC_SCHEMA}/{UC_VOLUME}")
