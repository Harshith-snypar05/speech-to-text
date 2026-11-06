from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

A = "manual_assets"
ACCENT = RGBColor(0xE0, 0x8A, 0x00)

doc = Document()

style = doc.styles["Normal"]
style.font.name = "Calibri"
style.font.size = Pt(12)

title_style = doc.styles["Title"]
title_style.font.size = Pt(30)

# ---- Title page ----
doc.add_heading("How to Use the App", level=0)
p = doc.add_paragraph(
    "This guide walks you through everything, step by step, with a picture for every step. "
    "Wherever you see an orange circle, box, or arrow in a picture, that is the exact spot to "
    "tap or click."
)
p.runs[0].font.size = Pt(13)
doc.add_paragraph()
doc.add_page_break()


def add_step(number, title, body_lines, image, caption=None, width_in=5.8):
    heading = doc.add_heading(f"{number}. {title}", level=1)
    for run in heading.runs:
        run.font.color.rgb = ACCENT
    for line in body_lines:
        para = doc.add_paragraph(line)
        para.paragraph_format.space_after = Pt(8)
        para.runs[0].font.size = Pt(12.5)
    img_para = doc.add_paragraph()
    img_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = img_para.add_run()
    run.add_picture(f"{A}/{image}", width=Inches(width_in))
    if caption:
        cap = doc.add_paragraph(caption)
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.runs[0].italic = True
        cap.runs[0].font.size = Pt(10.5)
        cap.runs[0].font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    doc.add_paragraph()


# ---- Step 1: Sign in ----
add_step(
    1, "Signing In",
    [
        "When you open the app, you will see a sign-in page first. This keeps the app private "
        "so only people who have been given an email and password can get in.",
        "Type the email into the first box, and the password into the second box. Then tap or "
        "click the blue \"Log In\" button.",
    ],
    "final_01_login.png",
    "The orange box shows the two boxes to fill in, and the button to tap after.",
)

# ---- Step 2: Home screen / start session ----
add_step(
    2, "Starting a New Recording",
    [
        "Once you are signed in, you will land on the main page. This is where every recording "
        "you have made before will show up under \"Recent Transcripts\".",
        "To begin a brand new recording, tap or click the blue \"Start New Session\" bar at the "
        "top.",
    ],
    "final_02_home.png",
    "The orange box marks the bar that starts a new recording.",
)

# ---- Step 3: the settings screen ----
add_step(
    3, "What the Settings Screen Lets You Change",
    [
        "Tap or click the small gear icon in the top-left corner of the recording page to open "
        "Settings. From here you can change a few simple things:",
        "•  Text size — make the words on screen smaller or bigger (S, M, or L).",
        "•  Theme — choose a light look, a dark look, or let it match your device.",
        "•  Microphone — pick which microphone to use for recording, if your device has "
        "more than one.",
        "•  Log out — sign out of the app. The next person to open it will need to sign "
        "in again.",
    ],
    "final_07_settings.png",
    "Each orange box marks one of the four things you can change.",
)

# ---- Step 4: access code ----
add_step(
    4, "Adding a Secret Code to Your Recording (Optional)",
    [
        "Before you start recording, you can turn on \"Require access code\". This adds a secret "
        "code to the link you will share later, so you have one extra layer of control over who "
        "can watch.",
        "You do not have to turn this on — the app works perfectly fine without it. It is "
        "simply there if you want it.",
    ],
    "final_04_access_code.png",
    "The orange box marks the switch. Blue means it is turned on.",
)

# ---- Step 5: recording ----
add_step(
    5, "Recording and Watching Your Words Appear",
    [
        "Tap or click the big round microphone button to start. The button turns red and the "
        "words you say will start appearing on the screen, live, as you speak.",
        "To stop recording, tap or click the same button again.",
    ],
    "final_05_recording.png",
    "The orange circle marks the microphone button, which turns red while recording.",
)

# ---- Step 6: drag up ----
add_step(
    6, "Seeing Everything You Have Said So Far",
    [
        "While you are recording, only a small strip at the very bottom of the screen shows the "
        "latest words. To see everything said from the beginning, place your finger (or your "
        "mouse) on that strip and drag it upward.",
        "This opens up a larger panel that scrolls on its own as you keep talking, so the newest "
        "words are always in view.",
    ],
    "final_06_drag_handle.png",
    "The orange arrow shows the strip to drag upward.",
)

# ---- Step 7: share link ----
add_step(
    7, "Getting a Link So Someone Else Can Watch Live",
    [
        "While recording, tap or click the share icon in the top-right corner. This opens a box "
        "with a link.",
        "Anyone you send this link to can open it on their own phone or computer and watch your "
        "words appear live, without needing to sign in themselves. They cannot speak or change "
        "anything — they can only watch and read.",
        "Tap or click the copy icon to copy the link, or tap or click \"Share Link\" to send it "
        "directly through your device's own sharing options (for example, Messages or Email). If "
        "you turned on the secret code in step 4, it is already included in this link, so you do "
        "not need to send it separately.",
    ],
    "final_08_share_link.png",
    "The top orange box is the link itself. The bottom orange box is the Share Link button.",
)

# ---- Step 8: end session ----
add_step(
    8, "Ending Your Recording",
    [
        "When you are finished speaking, tap or click \"End Session\", just below the microphone "
        "button. This stops the recording and finishes everything for anyone who was watching "
        "live.",
    ],
    "final_09_end_session.png",
    "The orange box marks the End Session button.",
)

# ---- Step 9: saved ----
add_step(
    9, "Your Recording Is Saved Automatically",
    [
        "As soon as you end the recording, it is saved by itself — there is nothing extra "
        "you need to do. You will be taken back to the main page, and your new recording will "
        "appear at the top of \"Recent Transcripts\", with the date and a short preview of what "
        "was said.",
        "Tap or click it at any time afterward to read the full text again.",
    ],
    "final_10_saved.png",
    "The orange box marks the newly saved recording on the main page.",
)

# ---- Step 10: link after ending ----
add_step(
    10, "What Happens to the Link After You End the Recording",
    [
        "The link you shared in step 7 keeps working even after you end the recording — it "
        "does not break or disappear.",
        "If someone opens it after you have stopped, they will see a note saying the speaker has "
        "ended the session, followed by the complete text of everything that was said from start "
        "to finish. They are simply reading it now, instead of watching it appear live.",
    ],
    "final_11_ended_link.png",
    "The orange box marks the \"Session ended\" note a viewer sees after you stop.",
)

doc.save(f"{A}/../ST_Transcribe_User_Manual.docx")
print("saved")
