<div align="center">
  <h1>AI CRM 🤖</h1>
  <p><strong>A Next-Generation, AI-Powered CRM and Social Media Automation Suite built for Frappe</strong></p>
</div>

## 🌟 Overview

**AI CRM** transforms your Frappe ERP into a highly autonomous, intelligent workspace. Built as an advanced orchestration layer on top of [FinByz AI](https://github.com/finbyz/finbyzai), this application automates the most time-consuming aspects of Sales, Human Resources, and most importantly, **Social Media Marketing & Content Repurposing**.

Deploy AI bots to read and engage on Reddit, schedule rich-media posts to LinkedIn and Twitter (X), or automatically extract and summarize YouTube videos into actionable CRM content—all working 24/7 as your digital workforce.

## ✨ Core Modules

### 1. 📱 Multi-Platform Social Media Automation (LinkedIn & Twitter)
Forget third-party scheduling tools. AI CRM includes native, secure OAuth 2.0 integrations with major social networks:
- **LinkedIn Integration**: Post text and rich media (images) directly to LinkedIn Company Pages or Personal Profiles using the latest LinkedIn Posts API.
- **Twitter (X) Integration**: Supports Twitter OAuth 2.0 with PKCE, allowing you to schedule tweets and upload media (supporting chunked video/image uploads) natively from Frappe.
- **Automated Dispatcher**: The `schedule_social_media_posts` background worker runs every 10 minutes, ensuring your AI-generated or manually curated content is reliably published across all connected platforms simultaneously.

### 2. 🎥 YouTube Content Fetching & Repurposing
Extract massive value from video content without watching it:
- **YouTube Transcription Tool**: The built-in `get_youtube_video_transcription` LangChain tool allows AI agents to instantly extract captions/transcripts from any YouTube video URL.
- **Automated Workflow**: Through the `YouTube Videos` doctype, you can enqueue background jobs (`enqueue_youtube_workflow`) that fetch, process, analyze, and summarize videos, perfectly converting long-form video into blog posts, social media snippets, or internal knowledge base documents.

### 3. 🌐 Autonomous Reddit Engagement
Turn Reddit into an automated lead-generation and brand-awareness engine:
- **Trend Fetching**: An hourly background job (`fetch_reddit_posts`) continuously scans targeted subreddits for relevant discussions based on your configured industry keywords.
- **Smart Auto-Commenting**: Leverages LLMs to evaluate fetched posts. If a post is relevant, the AI automatically drafts and publishes highly contextual, helpful comments to drive organic engagement back to your brand (`process_pending_ai_comments`).

### 4. 📄 AI HR & Resume Ranker
- **Automated Resume Parsing**: Hooked into Frappe's native `Job Applicant` doctype. The moment a resume is uploaded, the AI parses the document.
- **Intelligent Ranking**: Evaluates the candidate's parsed skills against the linked `Job Opening` requirements, generating an instant match score.

### 5. 💬 Smart Communication Intelligence
- **Follow-up Generation**: Hooks into `Lead` and `Customer` interactions (`generate_followups_on_party_activity`). It analyzes communication logs and automatically suggests or generates the next best action, ensuring deals never slip through the cracks.

## ⚙️ Architecture

This app extends the Frappe framework heavily utilizing document hooks and scheduled background tasks:
- **Event Hooks**: Triggers real-time AI processing `after_insert` on `Job Applicant`, `Lead`, and `Customer`.
- **Scheduled Tasks**: Utilizes Frappe's robust scheduler mechanism (Cron, Hourly, Daily) to handle asynchronous operations like Reddit scraping, YouTube transcript fetching, and Social Media dispatching without affecting core ERP performance.
- **FinByz AI Core**: Relies strictly on `finbyzai` for LLM routing and agent execution.

## 🚀 Installation

### Prerequisites
AI CRM requires **FinByz AI** to function. Ensure `finbyzai` is installed on your bench first.

### Setup

```bash
cd $PATH_TO_YOUR_BENCH

# Fetch the application from the repository
bench get-app https://github.com/finbyz/ai_crm.git --branch develop

# Install the application on your target site
bench --site [your-site-name] install-app ai_crm
```

## 🛠️ Configuration Guide

### 1. Setup Social Media (LinkedIn / Twitter)
1. Navigate to **LinkedIn Integration** or **Twitter Integration** in Frappe Desk.
2. Enter your Client ID and Client Secret, then initiate the secure OAuth 2.0 flow to authorize the app.
3. Once authenticated, use the **Content Hub Setting** to configure auto-posting rules and default AI Agents.

### 2. Setup YouTube Automation
1. Navigate to **YouTube Settings** and configure your API keys (if using official APIs) or rely on the built-in transcript scraper tool.
2. Provide a YouTube Video URL in the **YouTube Videos** doctype and click process to begin the automated extraction and summarization workflow.

### 3. Setup Reddit Automation
1. Enter your Reddit API credentials in the Reddit automation settings.
2. Specify the target subreddits and keywords.
3. Ensure your bench scheduler is running (`bench enable-scheduler`) so the hourly cron jobs can dispatch posts and fetch threads.

## 🤝 Contributing

This app uses `pre-commit` for code formatting and linting. Please ensure you format your code before submitting a Pull Request.

```bash
cd apps/ai_crm
pre-commit install
```
Code standards are enforced via:
- `ruff`
- `eslint`
- `prettier`
- `pyupgrade`

## 📄 License

This project is licensed under the **GPL-3.0** License.
