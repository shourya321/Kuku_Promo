"""Writes a second synthetic show (modern billionaire revenge, 4 episodes) to test generalisation.

  python tools/make_revenge_show.py sample_input/revenge_show

It deliberately uses formatting quirks the parser was NOT originally written for:
  * Windows CRLF line endings          * hh:mm:ss.ff timestamps instead of mm:ss.ff
  * Title-case headers (**Camera:**)    * file names Ep_01.txt instead of episode-001-*.txt
  * episode 1 has no CAMERA blocks at all (so cuts can only snap to dialogue gaps)
All story text is original, written for this repo.
"""
import sys
from pathlib import Path

# (header, delivery, text, seconds). header "Camera"/"Action"/"SFX" = structural, anything else = speaker
EPISODES = {
    1: ("Nora is fired and humiliated at her ex-husband's engagement party, not knowing who the waiter is.",
        "Opens the series.", [
        ("Action", "", "A glittering rooftop party. Nora, in a cheap coat, is stopped at the velvet rope.", 3.0),
        ("GRANT", "Smug", "Look who crawled out of the divorce. Security, she's not on the list.", 3.6),
        ("NORA", "Steady", "I'm not here for you, Grant. I'm here for my mother's ring.", 3.4),
        ("VIVIENNE", "Sneering", "This ring? Grant gave it to me. Finders keepers.", 3.0),
        ("Action", "", "Vivienne throws a glass of champagne in Nora's face. Guests laugh.", 2.6),
        ("SFX", "", "The crowd's laughter, phones clicking.", 1.6),
        ("GRANT", "Cold", "You were nothing before me. You're nothing after me.", 3.2),
        ("NORA", "Shaking", "That ring is the only thing my mother left me.", 3.0),
        ("VIVIENNE", "Mocking", "Then beg. On your knees, in front of everyone.", 3.0),
        ("Action", "", "A waiter steps between them and quietly takes the ring from Vivienne's hand.", 3.0),
        ("ELIAS", "Calm, Dangerous", "The lady asked for her ring.", 2.2),
        ("GRANT", "Furious", "Who do you think you are? You pour drinks.", 2.8),
        ("ELIAS", "Quiet", "I own the building you're standing on, Mr. Hale.", 3.2),
        ("Action", "", "Every phone in the room lowers. Grant goes pale.", 2.4),
        ("NORA", "Stunned, Whispering", "Elias? You were supposed to be dead.", 3.0),
        ("SFX", "", "A low boom of music, then silence. Cliffhanger.", 2.0),
    ]),
    2: ("Elias offers Nora a deal: marry him for one year and he will help her take back her father's company.",
        "Follows episode 1's rooftop.", [
        ("Camera", "", "Close on Nora's wet face in an elevator mirror.", 2.0),
        ("ELIAS", "Measured", "Five years ago your father saved my life. Tonight I repay it.", 3.6),
        ("NORA", "Wary", "People don't come back from the dead to be kind.", 3.0),
        ("ELIAS", "Flat", "No. They come back to collect. Grant stole your father's company.", 3.6),
        ("Camera", "", "The elevator opens on a penthouse full of lawyers.", 2.0),
        ("LAWYER", "Brisk", "One year of marriage. Fifty-one percent of Hale Holdings at the end.", 3.6),
        ("NORA", "Sharp", "And what do you get?", 1.8),
        ("ELIAS", "Cold", "Grant on his knees. The way you were tonight.", 3.0),
        ("Action", "", "Nora signs. Elias slides her mother's ring onto her finger.", 3.0),
        ("Camera", "", "Cut to Grant's office. Vivienne watches the signing on a hidden camera feed.", 2.6),
        ("VIVIENNE", "Venomous", "She married him? Then she dies before the honeymoon.", 3.2),
        ("GRANT", "Alarmed", "Vivienne, what did you do?", 2.0),
        ("VIVIENNE", "Smiling", "I hired his driver.", 2.0),
        ("Camera", "", "Nora and Elias step into a black car. The driver locks the doors.", 2.6),
        ("SFX", "", "Click of the door locks. Engine roars. Cliffhanger.", 1.8),
    ]),
    3: ("The car crash plot fails; Nora discovers Elias has been lying about why he really chose her.",
        "Follows episode 2's car.", [
        ("Camera", "", "The car swerves through rain at high speed.", 2.0),
        ("ELIAS", "Commanding", "Nora, get down. Now.", 1.6),
        ("Action", "", "Elias grabs the wheel; the car spins into a guardrail.", 2.6),
        ("SFX", "", "Metal screaming against metal.", 1.4),
        ("Camera", "", "Smoke. The driver is gone. Elias is bleeding.", 2.0),
        ("NORA", "Terrified", "You're bleeding. Elias, stay with me.", 2.6),
        ("ELIAS", "Weak", "Whatever you find in my phone... I'm sorry.", 3.0),
        ("Action", "", "Nora opens his phone. A photo: her father, alive, in a hospital bed.", 3.0),
        ("NORA", "Shocked", "My father died three years ago. I buried him.", 3.0),
        ("Camera", "", "Close on the photo's date stamp: last week.", 2.0),
        ("NORA", "Breaking", "You knew. You knew he was alive and you married me anyway.", 3.4),
        ("ELIAS", "Fading", "I married you because he asked me to protect you.", 3.0),
        ("Action", "", "Headlights appear. Grant steps out of a car, holding a gun.", 2.6),
        ("GRANT", "Cold", "Hand me the phone, Nora. Your father stays dead.", 3.0),
        ("SFX", "", "A gunshot rings out. Cut to black.", 1.6),
    ]),
    4: ("Nora turns Grant's own investors against him at the shareholder meeting.",
        "Follows episode 3's gunshot.", [
        ("Camera", "", "A boardroom. Grant at the head of the table, smiling.", 2.0),
        ("GRANT", "Triumphant", "The vote is a formality. Hale Holdings stays mine.", 3.2),
        ("Action", "", "The doors open. Nora walks in, a bandaged Elias behind her.", 2.6),
        ("VIVIENNE", "Panicked", "You're supposed to be...", 1.8),
        ("NORA", "Icy", "Dead? You keep saying that about my family.", 2.8),
        ("NORA", "Firm", "Fifty-one percent. I vote to remove Grant Hale as CEO.", 3.4),
        ("GRANT", "Laughing", "You can't. Your shares aren't valid for a year.", 3.0),
        ("ELIAS", "Calm", "They are if the founder signs them over himself.", 3.0),
        ("Camera", "", "The doors open again. Nora's father walks in on a cane.", 2.4),
        ("FATHER", "Weak but Fierce", "Hello, Grant. Remember the hospital you left me in?", 3.4),
        ("Action", "", "Investors stand. Grant backs against the window.", 2.4),
        ("VIVIENNE", "Desperate", "Grant, tell them it was your idea, not mine.", 3.0),
        ("GRANT", "Snapping", "Shut up, Vivienne.", 1.6),
        ("NORA", "Quiet", "Security. He's not on the list.", 2.4),
        ("SFX", "", "Grant's phone buzzes. A text: 'I know who really shot Elias.' Cliffhanger.", 2.4),
    ]),
}


def ts(t):
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:05.2f}"


def write(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    for n, (logline, cont, lines) in EPISODES.items():
        parts = [f"EPISODE NUMBER: Episode {n}", f"EPISODE LOGLINE: {logline}", f"CONTINUITY NOTES: {cont}", "",
                 "--- SCRIPT START ---", "", "SCENE 01", "Scene heading: INT. CITY - NIGHT"]
        t = 0.0
        body = []
        for head, deliv, text, dur in lines:
            if head in ("Camera", "Action", "SFX"):
                h = head
            else:
                h = f"{head} ({deliv})" if deliv else head
            q = f'"{text}"' if head not in ("Camera", "Action", "SFX") else text
            body += [f"**{h}:**", f"Start: ({ts(t)}) | End: ({ts(t + dur)})", q, ""]
            t = round(t + dur, 2)
        parts += [f"Scene start: {ts(0)}", f"Scene end: {ts(t)}", "", "Actions and dialogue:", ""] + body + ["--- SCRIPT END ---"]
        (out / f"Ep_{n:02d}.txt").write_bytes("\r\n".join(parts).encode("utf-8"))   # CRLF on purpose
    print("wrote", out)


if __name__ == "__main__":
    write(Path(sys.argv[1] if len(sys.argv) > 1 else "sample_input/revenge_show"))
