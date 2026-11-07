"""Writes a small SYNTHETIC show in Kuku's screenplay format (so the public repo has a demo
without Kuku's confidential pack). Original story, written for this project."""
from pathlib import Path

def ts(t):
    m = int(t // 60); return f"{m:02d}:{t - 60*m:05.2f}"

EPISODES = [
 ("The Waitress Was the Heiress", "At her ex's engagement party, waitress Mia is humiliated by his new fiancée, until a stranger in a grey suit takes her side.",
  "First episode.", [
  ("INT. ROOFTOP RESTAURANT – NIGHT", [
   ("CAMERA", "", "Wide shot of a glittering rooftop party, champagne towers and string lights.", 3.0),
   ("ACTION", "", "Mia, in a black waitress uniform, carries a tray of glasses through the crowd.", 3.0),
   ("SLOANE (Sneering)", "D", "Careful. That tray costs more than your rent.", 2.6),
   ("CAMERA", "", "Close-up on Mia's grip tightening on the tray.", 2.0),
   ("MIA (Quiet, Steady)", "D", "Congratulations on the engagement, Miss Sloane.", 2.8),
   ("SLOANE (Mocking)", "D", "Ryan told me you two dated. For three years.", 3.0),
   ("SLOANE (Cruel)", "D", "Three years, and he still chose me.", 2.4),
   ("ACTION", "", "Sloane tips her red wine slowly over the front of Mia's white collar.", 3.2),
   ("SOUND FX", "", "A collective gasp from the guests.", 1.5),
   ("CAMERA", "", "Close-up on wine dripping from Mia's chin.", 2.0),
   ("RYAN (Uncomfortable)", "D", "Sloane, that's enough.", 1.8),
   ("SLOANE (Icy)", "D", "Is it? She should get on her knees and clean that up.", 3.2),
   ("ACTION", "", "Mia slowly kneels to pick up the broken glass, her jaw tight.", 3.0),
   ("CAMERA", "", "Low angle on polished Italian shoes stepping into frame beside her.", 2.4),
   ("STRANGER (Calm, Dangerous)", "D", "Stand up. Nobody kneels in my building.", 3.0),
   ("SLOANE (Laughing)", "D", "Your building? Who do you think you are?", 2.8),
   ("CAMERA", "", "Close-up on the stranger handing Mia his handkerchief, eyes never leaving Sloane.", 3.0),
   ("STRANGER (Quiet)", "D", "The man who signs your fiance's paycheck.", 2.8),
   ("CAMERA", "", "Ryan's face drains of colour.", 2.0),
   ("SOUND FX", "", "Low ominous synth swell to a cliffhanger peak.", 2.0),
   ("CAMERA", "", "Cut to black.", 1.0)])]),
 ("The Contract", "The stranger, billionaire Adrian Vale, offers Mia a contract: be his fiancée for 30 days and he will ruin the people who humiliated her.",
  "Follows episode 1's rooftop confrontation.", [
  ("INT. PENTHOUSE OFFICE – NIGHT", [
   ("CAMERA", "", "Slow push-in on a contract sliding across a glass desk.", 3.0),
   ("ADRIAN (Matter-of-fact)", "D", "Thirty days. You play my fiancée.", 2.6),
   ("MIA (Stunned)", "D", "You don't even know my last name.", 2.4),
   ("ADRIAN (Knowing)", "D", "Your name is Mia Hart. Your mother died owing my company two million dollars.", 4.2),
   ("CAMERA", "", "Close-up on Mia freezing.", 2.0),
   ("MIA (Shaken)", "D", "How do you know that?", 1.8),
   ("ADRIAN (Cold)", "D", "I know everything about the people I choose.", 2.6),
   ("ACTION", "", "Mia picks up the pen, hesitates over the signature line.", 3.0),
   ("MIA (Wary)", "D", "And what do I get?", 1.6),
   ("ADRIAN (Smiling)", "D", "The debt disappears. And Sloane loses everything.", 3.2),
   ("CAMERA", "", "Extreme close-up of the pen touching the paper.", 2.0),
   ("SOUND FX", "", "The office door bursts open.", 1.2),
   ("RYAN (Furious)", "D", "Mia! Don't sign that! You have no idea what he did to your mother!", 3.8),
   ("CAMERA", "", "Mia looks from Ryan to Adrian, pen frozen.", 2.4),
   ("ADRIAN (Dangerously calm)", "D", "Tell her, Ryan. Tell her who really sold her mother's house.", 3.6),
   ("CAMERA", "", "Close-up on Ryan, guilt flashing across his face.", 2.2),
   ("SOUND FX", "", "Sharp string sting, cliffhanger peak.", 1.6),
   ("CAMERA", "", "Cut to black.", 1.0)])]),
 ("Ryan's Secret", "Ryan confesses his family profited from Mia's mother's ruin, while Sloane plots to expose the fake engagement.",
  "Follows episode 2's confrontation in the penthouse.", [
  ("INT. PENTHOUSE OFFICE – NIGHT", [
   ("CAMERA", "", "Medium shot on Ryan swallowing hard.", 2.0),
   ("RYAN (Ashamed)", "D", "My father bought the debt. We took the house.", 3.0),
   ("MIA (Broken)", "D", "You were sleeping in my bed while your family took my mother's home?", 3.8),
   ("ACTION", "", "Mia slaps Ryan hard across the face.", 1.4),
   ("SOUND FX", "", "A sharp crack of the slap.", 0.6),
   ("CAMERA", "", "Close-up on Ryan's stunned face, a red mark blooming.", 2.0),
   ("MIA (Shaking, Fierce)", "D", "Get out.", 1.2),
   ("ACTION", "", "Ryan leaves. Mia turns and signs the contract in one stroke.", 3.0),
   ("ADRIAN (Approving)", "D", "Welcome to the family, Miss Hart.", 2.4)]),
  ("INT. SLOANE'S CAR – NIGHT", [
   ("CAMERA", "", "Sloane in the back seat, phone glowing on her face.", 2.6),
   ("SLOANE (Venomous)", "D", "A waitress engaged to Adrian Vale overnight? It's fake.", 3.4),
   ("SLOANE (Scheming)", "D", "Find me proof. And find out who her father really is.", 3.4),
   ("CAMERA", "", "Close-up of the phone screen: a photo of Mia as a child beside a man in a military uniform.", 3.0),
   ("SLOANE (Shocked, Whispering)", "D", "No... that's impossible.", 2.2),
   ("SOUND FX", "", "Ominous drone to a cliffhanger peak.", 1.8),
   ("CAMERA", "", "Cut to black.", 1.0)])]),
]

def build(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    for n, (title, logline, notes, scenes) in enumerate(EPISODES, 1):
        t, lines = 0.0, [f"EPISODE NUMBER: Episode {n}", f"EPISODE LOGLINE: {logline}", f"CONTINUITY NOTES: {notes}", "", "--- SCRIPT START ---", ""]
        for k, (heading, blocks) in enumerate(scenes, 1):
            dur = sum(b[3] for b in blocks)
            lines += [f"SCENE {k:02d}", f"Scene heading: {heading}", f"Scene start: {ts(t)}", f"Scene end: {ts(t + dur)}", "", "Actions and dialogue:", ""]
            for name, kind, text, d in blocks:
                header = name if kind == "" else name
                body = f'"{text}"' if kind == "D" else text
                lines += [f"**{header}:**", f"Start: ({ts(t)}) | End: ({ts(t + d)})", body, ""]
                t += d
        lines += ["--- SCRIPT END ---"]
        (out / f"episode-{n:03d}-Demo.txt").write_text("\n".join(lines), encoding="utf-8")

if __name__ == "__main__":
    build(Path(__file__).resolve().parent.parent / "sample_input" / "demo_show")
