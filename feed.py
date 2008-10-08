import feedparser

# http://feedparser.org/docs/

feed = feedparser.parse('http://www.mininova.org/rss.xml?user=EZTV')

print(feed.feed.title)
print(feed.feed.subtitle)

for entry in feed.entries:
    print(entry.title)
    print(entry.link)
    print(entry.updated_parsed)
