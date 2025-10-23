# Copyright (c) 2025, Finbyz Tech Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
import requests
import time
from datetime import datetime
from pytrends.request import TrendReq

class TrendingTopicGenerator(frappe.model.document.Document):

    def publish_progress(self, message, percent=None):
        frappe.publish_realtime(
            "trending_topic_progress",
            {"message": message, "percent": percent, "docname": self.name},
            user=frappe.session.user,
            doctype=self.doctype,
            docname=self.name
        )
        time.sleep(0.2)

    @frappe.whitelist()
    def fetch_trending_content(self):
        """Fetch trending topics via Google Trends → top 3 queries → news via SerpApi"""
        if not self.keywords:
            frappe.throw("Please enter keywords")

        self.generated_topics = []
        self.publish_progress("🚀 Starting trending content fetch...", 5)

        pytrends = TrendReq(hl='en-US', tz=360)
        api_key = "36607041a5eebe2bf4fad30ad700a60947f8078bb719e07607ebf5436780f030"

        keywords = [kw.strip() for kw in self.keywords.split(",") if kw.strip()]
        all_content = []

        for idx, keyword in enumerate(keywords, 1):
            self.publish_progress(f"🔍 Fetching Google Trends for '{keyword}'...", 10 + idx*10)
            try:
                pytrends.build_payload([keyword], timeframe='now 7-d')
                related_trends_df = pytrends.related_queries().get(keyword, {}).get('top')
                top_trends = [keyword]  # include main keyword
                if related_trends_df is not None:
                    top_trends += list(related_trends_df.head(3)['query'])
            except Exception as e:
                frappe.log_error(f"Google Trends fetch failed for '{keyword}': {str(e)}", "Google Trends Error")
                top_trends = [keyword]

            for trend_query in top_trends:
                self.publish_progress(f"📰 Fetching news for '{trend_query}' via SerpApi...", 30 + idx*10)
                try:
                    url = f"https://serpapi.com/search.json?q={trend_query}&tbm=nws&num=10&hl=en&api_key={api_key}"
                    resp = requests.get(url, timeout=10)
                    resp.raise_for_status()
                    data = resp.json()
                    news_results = data.get("news_results", [])

                    for article in news_results:
                        title = article.get("title", "")[:140]  # truncate title
                        description = article.get("snippet", "")  # full snippet
                        source_content = f"""**Source:** {article.get('source', '')}
**Keyword:** {trend_query}
**URL:** {article.get('link', '')}
**Published:** {article.get('date', '')}
**Content:** {article.get('snippet', '')}"""

                        self.append("generated_topics", {
                            "topic_title": title,
                            "description": description,
                            "source_keyword": trend_query,
                            "source_content": source_content
                        })
                except Exception as e:
                    msg = f"SerpApi News fetch failed for '{trend_query}': {str(e)}"
                    frappe.log_error(msg, "SerpApi Error")
                    # Add the error in child table with title truncated to 140
                    self.append("generated_topics", {
                        "topic_title": msg[:140],
                        "description": msg,
                        "source_keyword": trend_query,
                        "source_content": msg
                    })

        self.last_generated_on = datetime.now()
        self.source_summary = f"Fetched {len(self.generated_topics)} items from Google Trends & SerpApi"
        self.save(ignore_permissions=True)

        self.publish_progress("🎉 Trending content fetch complete!", 100)
        frappe.msgprint(f"✅ Successfully fetched {len(self.generated_topics)} trending items!", title="Success", indicator="green")

        return {"status": "success", "items_fetched": len(self.generated_topics)}
