import feedparser

# http://feedparser.org/docs/

# feeds:
# http://www.mininova.org/rss.xml?user=EZTV
# http://tvrss.net/
# http://www.torrentleech.org/ <- invite only

feed = feedparser.parse('http://tvrss.net/search/index.php?show_name=NCIS&show_name_exact=true&mode=rss')

print(feed.feed.title)
print(feed.feed.subtitle)

for entry in feed.entries:
    print(entry.title)
    print(entry.link)
    print(entry.updated_parsed)

