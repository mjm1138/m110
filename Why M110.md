# Why M110?

## What Led me Here
My Astrophotography journey started in early 2026, when I got a Seestar S50 Smart Telescope. The ease of use amazed me, and the mobile app made it fun and easy to pick targets. I quickly started amassing a large collection of objects. But I ran into two problems:

First, how do I keep track of all of these images and objects? Which ones need more integration time? Which ones haven’t been processed? I was barely keeping up with spreadsheets and a sprawling directory of lights, processed images and intermediate files.

Second, how do I decide what to capture next? What is my goal? The app made it pretty easy to see what would be in the sky tonight and set up a plan, but I was losing track of what I’d already seen and felt like I might be missing out on good views.

## My Beginner’s Journey
I decided to collect the Messier catalog. It’s a manageable size at 110 objects, and most of them are great candidates for a smart scope like the S50. There’s a nice variety of objects, and they’re all visible where I live.

At the same time, I started working with an LLM (Claude) to build a set of scripts and a hierarchy of data files and documents to keep track of my library, track my progress through the catalog, and make recommendations for capture sessions so I can keep building toward the goal of capturing all 110 objects. It worked pretty well! I was getting exposed to all kinds of fascinating objects, and having fun watching my Messier collection grow.

Meanwhile, in social media groups and forums, I noticed that other folks who are new to the hobby were running into the same issues: Keeping track of a growing collection, and feeling uncertain about “where to go” in Astrophotography. I decided my framework would make a good app, and might help others stay organized and stay engaged. M110 was born.

## The M110 App
M110 is designed from the start to be cross-platform, lightweight, low-friction, and open-source. It will import pictures from your Seestar smart telescope, organize them, prepare them for processing in Siril, and display or even publish them. It will track your progress through the Messier catalog or a variety of other catalogs and collections, with selections for users in the northern and southern hemispheres. 

By optionally connecting Claude or another LLM, M110 will provide a session planning skill that can help you build imaging session plans for your smart telescope. It finds targets that work for your location, your horizon, local light pollution bubbles, and the current lunar phase. It orders and schedules objects so you’re capturing them at peak visibility. It can prepare field guides for when you’re planning a trip to a remote site, offer advice on processing workflow and capture settings, and even critique your results if you like.

M110 keeps track of what’s in season, what you’ve captured, and what needs more integration time, so the session planner can work strategically to help you reach your collection goals. You can tune your preferences for what kinds of objects you like, and whether you want to capture the most objects possible, or create deep stacks for the best possible image results. It builds a priorities list that you can examine, fine tune, and regenerate at any time.

If you don’t want to use an LLM, M110’s core functions of collection tracking, organization, display, prioritization, and image processing workflow management will work just fine. 

Ultimately I want to see M110 grow to handle images from other smart telescopes and astrophotography rigs, as well as desktop processing workflows beyond Siril. I’m having a lot of fun developing and using M110, and I hope you’ll have fun with it too!

M110 is developed in Python on macOS using Claude Code and other tools. It is targeted to run on macOS, Linux and Windows. Source code is available at [repo], where merge requests, bug reports and other contributions are welcome. It is free for you to use, modify, and redistribute under the terms of version 2.0 of the Apache License.