**Incomplete document...WIP**

LUCY ARCHITECTURE DESIGN CHOICES:



Ever-growing library of short, purposeful shell commands that include using LLMs to perform complex tasks - Much faster and executes right away on the system if a command or chain of commands could resolve the user's request. Requests that are familiar get executed right away, reliably assuming the commands are battle tested and work across different systems and environments.



**PROS:**

* Much faster - executes directly on the user's computer which rich access and control over the OS thanks to the OS shell.
* Flexible system capable of handling both simple and complex tasks
* On-demand LLM calls only when it's actually needed for example writing help, web searching (will switch to formatted google results instead of llms). API free tiers or their web counterparts are sufficient as the user wouldn't require an LLM for most of their tasks assuming the library, search, and sorting functions cover a wide variety of tasks, are flexible, and fast at executing commands.



**CONS:**

* Needs active maintenance over the commands library and needs to keep growing to support new and complex tasks
* Needs a highly flexible searching function that returns the most relevant command(s) for the user's prompt.
* Needs a way to correctly order/sort these search results to execute not only a single command but most likely and most of the time, chain together  multiple commands.

**ADDTIONAL NOTES:**

* Needs a decent feedback system that returns which function failed, what kind of error, at which line, etc. along with the system's current state and state at the time of the error's occurrence.
* text is better than voice interaction. There should be two modes Text and Voice mode with text being priority as per user feedback and research.


Toolkit:

Emailing: Use gmail's old interface on SMTP AND IMAP to send and read emails quickly.

Media playback: mainly you tube play any video (includes music cuz its on youtube), read comments, play the user's youtube playlists

Raylab to render 2D and 3D graphics for basic visualization.

Windows built in TTS to speak out all responses predefined ones + llm parsed responses.



New: 

so basically its called lucy and its basically in lay man terms siri but on steoroids for the personal computer. U can interact with it using text or voice mode just like siri but it does real work just like today's agentic ai tools on ur physical machine. Unique difference is the technology in the sense of the architecture and design choices altho coorrect me whats the diff between them in this context: It uses a hybrid approach of thats able to be faster, cheaper, and ever growing smarter than any agentic ai today. Ok might siund like fluff but hear me out: Basic agentic like loop of a request -> execution -> feedback -> adjust -> goal achieved -> stop and ask for new request is already done and working for basic tasks that aren't very application specific or long running tasks. But the unique thing is that it uses an LLM thats light weight and cheaper to run to do a task for the first time its being done then after the agentic loop works, lucy saves the approach's best simple and tested, self contained script on its servers and the next time that tasks or a similar task is requested by the user, it bypasses the LLM completely and fetches and executeds that saved "util" or method almost instantly -> And repeat. What this does is makes her more and more smarter, faster everytime its used. Not only user specific, but many general purpose tasks/usecases/commands are pre written into lucy's main library or server thats used foor general purpose inquery like opening an app, setting reminders or emailing just like siri's core features but thats lucy's  general knowledge. The rest are stored in a space allocated just for that user so their data isn't shared or their tasks aren't shared with others unless general purpose or utils. Voice mode if u dont even wanna be near the computer and just talk to it while it works for u or text mode just like chatgpt, u prompt it while working and it does work in the BG without stealing focus or both. 
