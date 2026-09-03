# Why This Design (Plain-Language Version)

`SYSTEM_DESIGN.md` has the full technical reasoning, capacity math, and component deep-dive. This is the short version — the argument you'd give someone in two minutes, without the numbers.

## The one-sentence version

**The workload is bursty and mostly idle, so the infrastructure should be bursty and mostly idle too — pay for compute only when there's actually work, instead of running a bigger always-on server just to survive rare spikes.**

## The problem in plain terms

The existing server predicts trail conditions the moment someone asks for one, one request at a time. That's the right tool for "a person looking at one trail on the website" — fast, simple, done.

It's the wrong tool for "recompute predictions for every trail, for the next 16 days, all at once" — which is what you'd want for a nightly refresh job, or to survive a sudden spike in visitors. Doing that through the same one-at-a-time server either takes a long time, or means keeping a much bigger server running 24/7 just so it's big enough for that one nightly rush.

## Why a queue in the middle at all

A queue's whole job is to let two things move at different speeds without either one waiting on the other. The batch job can dump 32,000 requests in one second and walk away — it doesn't sit there waiting for each one to finish. The workers pull from the queue as fast as they're able to, and if 32,000 requests show up at once, the queue just holds them; nothing is lost, nothing blocks.

Without the queue, you'd need the producer and the consumer to agree on a pace in real time — which is exactly the coordination problem a queue exists to remove.

## Why Lambda for the actual computing

Think of Lambda as "workers that appear when there's work and disappear when there isn't." When the nightly batch lands, AWS spins up as many of these workers as needed to chew through the backlog; five minutes later, when the queue's empty, they're gone and you stop paying for them.

Compare that to running your own fleet of servers: you'd have to guess how many you need for the worst night, keep that many running all the time (even at 3pm when nothing's happening), and manually add more if a spike is bigger than you guessed. Lambda does the "how many do I need right now" math for you.

## Why DynamoDB instead of just writing results into the existing database

Two reasons, one simple and one subtle:

- **Simple**: all this pipeline ever does is "look up the answer for this trail and this date." That's the simplest possible database operation, and DynamoDB is built to do exactly that, extremely fast, without needing the more complex features (joins, relationships) Postgres offers for a different kind of workload.
- **Subtle, but the real reason**: if 32,000 writes were hitting the *same* database that people are also reading from at that exact moment, the writes could slow the reads down — a website visitor checking one trail shouldn't have to wait because a batch job happens to be running. Keeping the write-heavy bulk job in a separate store means the two can never compete with each other.

## Why a "dead letter queue" for failures

If a request can never succeed (bad input) or keeps failing (something's down), retrying it forever just wastes effort, and throwing it away silently means nobody ever finds out something's broken. The dead-letter queue is a "failed attempts" bin: after a handful of retries, the system gives up on that one request, puts it aside, and sends an email — so a person finds out within minutes instead of noticing days later that a chunk of predictions are just missing.

## The honest tradeoff

This is genuinely more moving parts than "just make the server bigger" — a queue, a failure bin, alerts, a second database, permissions wiring between all of them. That complexity is real, and it wouldn't be worth it for steady, predictable traffic; a plain server would be simpler to build and reason about.

It's worth it here specifically *because* the demand is spiky and mostly-zero. The entire argument for this design collapses if the traffic pattern changes to "steady load all day, every day" — at that point, the simpler always-on server stops being wasteful and becomes the better choice again. Architecture should follow the shape of the actual problem, not a default preference for "serverless is fancier."
