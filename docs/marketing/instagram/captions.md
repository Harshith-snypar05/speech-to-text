# Instagram plan: ScriptLiv

You post everything. Nothing here is posted. Instagram differs from LinkedIn:
- Captions have no clickable links. Put the site and the waitlist form in the bio; say "link in bio". Use the Story link sticker for the waitlist (clickable).
- Feed is 4:5 (1080x1350). Stories and Reels are 9:16 (1080x1920). All files are ready in this folder.
- Short hooks, line breaks, 5-8 hashtags max. Put the hashtags at the end.
- Your own voice: first person, same story as LinkedIn. Fill placeholders yourself.

## Set up the account first

Bio (150 char max, edit as you like):
```
Live speech-to-text, built by me.
Words appear as you speak.
Web app live. Android: join the waitlist
```
- Name field: `ScriptLiv | Live speech to text` (name field is searchable).
- Link in bio: either your waitlist form or a link page with both `scriptliv.com` and the waitlist. IG allows several links. Add both.
- Profile photo: the S logo mark (`assets/branding/exports`, square mark if you have one).
- Highlights: create "Waitlist" and "Demo". Cover can be the S mark on purple. Put the waitlist story in "Waitlist".
- Switch to a Professional (Creator or Business) account for insights. Free.

## Feed and Story sequence (match the LinkedIn calendar)

| Day | Feed | Story | Reel |
|---|---|---|---|
| 1 | `feed/teaser-1-building.png` | `stories/teaser-1-building.png` | |
| 2 | `feed/teaser-2-appear.png` | `stories/teaser-2-appear.png` | |
| 3 | `feed/teaser-3-accents.png` | `stories/teaser-3-accents.png` | |
| 4 | | repost the reel to Story | `reels/logo-reveal-1080x1920.mp4` |
| 5-6 | carousel: `feed/carousel-00..07.png` (8 slides) | share carousel to Story | |
| 8 | `feed/fixed-before-after.png` | `stories/fixed-before-after.png` | |
| 10 | | repost the reel to Story | `reels/live-demo-1080x1920.mp4` |
| 11 | | `stories/waitlist.png` + link sticker, poll sticker | |
| 14 | `feed/waitlist-reminder.png` | `stories/waitlist.png` + link sticker | |

Upload feed images at full size. Upload the carousel in order. Use the Reel as the cover: pick a frame with the logo.

## Captions

### Day 1 (teaser 1)
Something is being built. 👀
A new way to turn your voice into words.
More soon.

#buildinpublic #startup #app #speechtotext

### Day 2 (teaser 2)
What if words appeared as you spoke?
Not after the meeting. While you are still talking.
Coming soon.

#buildinpublic #indiedev #speechtotext #ai

### Day 3 (teaser 3)
Built to follow real accents. Because nobody speaks like a textbook.
[One true sentence about why you care, e.g. what you noticed testing Indian English.]

#buildinpublic #indiedev #india #speechtotext

### Day 4 (reveal Reel)
Meet ScriptLiv. Live speech to text.
Words appear as you speak, and get fixed a moment later.
Web app is live: link in bio.
Android app is coming: waitlist is in the bio too.

#scriptliv #speechtotext #buildinpublic #startup #android

Cover frame: the logo. Add on-screen caption off (video already has the tagline).

### Day 5-6 (carousel)
ScriptLiv in 8 slides.
Live words. Fixed a moment later. Share a link, no sign-in. Built for real accents.
Try it free on the web: link in bio.
Android waitlist: also in bio.

Save this for later if you want to try it.

#scriptliv #speechtotext #productivity #accessibility #buildinpublic

### Day 8 (before/after)
"We will meat tomorrow at ten."
A moment later: "We will meet tomorrow at 10."
A second, more accurate check re-reads each line and fixes it in place.

Web app: link in bio.

#scriptliv #speechtotext #ai #buildinpublic

### Day 10 (demo Reel)
10 seconds. Words appear as they are spoken, then get corrected.
I built it so you do not have to wait until the end to read what was said.
Free to try on the web: link in bio. Android waitlist is there too.

#scriptliv #speechtotext #buildinpublic #productivity #india

### Day 14 (waitlist reminder)
The Android app is not out yet, but the waitlist is open.
Join for early access, and your feedback decides what I fix first.
Waitlist link in bio. Web app is live now.

#scriptliv #android #buildinpublic #indiedev

Add a real signup number only if you want to, otherwise leave it out.

## Story stickers (to use in Stories)

- Day 11 waitlist story: place the **Link sticker** under the button, text "Join the waitlist". Add a poll above: "Do you use live captions in meetings?" Yes / Not yet (a real question, not a fake stat).
- Day 8 or 10: **Question sticker**: "What would you use live speech-to-text for?" Reply with real answers, and reuse them (with permission) later.
- Tag nothing you do not own. Do not use music tracks you are not licensed for; on Reels use IG's in-app audio, or none.

## Engagement (do this, not just posting)

- Reply to every comment within the first hours.
- Spend 10 min a day commenting on posts from people who would use it (students, creators, accessibility, Indian dev and startup accounts). Real comments only, no pitch.
- First comment on each post: a question to the audience, e.g. "What would you use live transcription for first?"

## Notes

- No tracking links in captions (not clickable). UTM goes on the bio link: `?utm_source=instagram&utm_medium=social`.
- No fake counts, no invented testimonials.
- Re-render: `python docs/marketing/src/render_instagram.py`.
