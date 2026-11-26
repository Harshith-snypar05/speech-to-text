# Reddit: 3 value-first text posts

I could NOT read any subreddit's rules (Reddit blocks my fetch tool). Search only gave secondhand summaries. So "rules allow it" is NOT verified. You must read each sub's sidebar and Rules page before posting. If a rule says no, skip that post.

What secondhand sources say (unverified, links are third-party):
- r/SideProject: described as a place to share projects and get feedback. No official rules page found.
- r/alphaandbetausers: a 2021 mod comment says describe the app, include a tester sign-up link, and keep beta testing free. Another source says posting may need permission. Check.
- r/developersIndia: self-promotion "heavily restricted" (2025 mod post). Project posts go under the "I Made This" flair. A "Showcase Sunday" thread is said to run on the second Sunday of each month (that would be Sun 13 Dec 2026). Check.

Rules of thumb for all three:
- Account must look like a person: comment helpfully in the sub for 1-2 weeks first. Brand-new accounts get removed.
- Use your own account. Say you are the developer. Never use fake accounts or ask friends to upvote.
- One post per sub, no reposting if removed. Reply to every comment for 24 h.
- Fill the [brackets] with real things. I wrote no numbers, user counts or testimonials because none exist.
- Add `?utm_source=reddit&utm_medium=social&utm_campaign=<sub>` only if links are allowed.

---

## Post 1: r/SideProject (feedback post)

Title: I built live speech-to-text for meetings. What would you want it to do?

I kept missing points in meetings because I was typing notes while trying to listen. So I built ScriptLiv.

How it works:
- Words show up as you speak.
- A second, more accurate check re-reads each line a moment later and fixes it in place (for example "meat tomorrow" becomes "meet tomorrow").
- You can share a link so others follow the transcript live, no sign-in for them.
- I tuned it for Indian English accents.

Where it is: the web app is live and free to start. An Android app is coming and I am collecting a waitlist.

What I got wrong at first: [one real mistake from your build, in your words].

Honest question: what would make this worth using for you, and what is missing? Roast it if you like.

(Site: scriptliv.com. Add only if the sub allows links in posts, otherwise put it in a comment when asked.)

---

## Post 2: r/alphaandbetausers (tester call, send after the Android closed test is live)

Title: [Android] Looking for testers: live speech-to-text app (free)

I am the solo developer of ScriptLiv, a live speech-to-text app. I am running an Android closed test and need testers.

What it does: live transcription as you speak, fixed a moment later by a second check. Share a live link, history, search, export.

What I need from testers:
- Use it in 1-2 real conversations (meeting, lecture, call).
- Tell me where words were wrong, what felt slow, what confused you.

What you get: free early access, and your feedback decides what I fix first. No payment, no card.

To join: [WAITLIST_LINK] (asks for the Google account email you use on Play, so I can add you to the test).

Questions and bug reports welcome in the comments.

Note: Google may require a minimum number of testers for a fixed number of days. Do not state that number in the post, it is not what testers care about.

---

## Post 3: r/developersIndia (technical write-up, NO link in the post)

Title: What I learned tuning live transcription for Indian English

I am building a live speech-to-text tool and spent a while on one problem: a first-pass live transcript is fast but often wrong, especially with Indian accents and names.

What I tried:
1. [Approach 1, what happened, in your words]
2. A second, slower and more accurate pass that re-reads each finished line and replaces the first-pass text in place. Live words stay fast, final text gets better.
3. [Approach 3 / something that failed]

The trade-off I keep hitting: latency vs accuracy. [your real observation, e.g. what delay felt acceptable].

Questions for people who have built this: [one specific technical question, e.g. how do you handle code-switching between English and Hindi mid-sentence?]

(No promotion in the body. If asked, answer in a comment. If the sub has a Showcase thread, post the project link only there.)

---

## Not posting (unless you verify rules)

r/accessibility, r/speechtotext, r/indiehackers: I could not check these either. Skip unless you read the rules and they allow it.
