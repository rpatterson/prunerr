# -*- coding: utf-8 -*-
# 2008-10, Erik Svensson <erik.public@gmail.com>

import sqlalchemy as sa
import sqlalchemy.orm as orm

metadata = sa.MetaData()

shows_table = sa.Table('shows', metadata,
    sa.Column('name', sa.Unicode, primary_key=True),
    sa.Column('download', sa.Boolean, default=False),
)

qualities_table = sa.Table('qualities', metadata,
    sa.Column('name', sa.Unicode, primary_key=True),
    sa.Column('score', sa.Integer, default=0),
)

episodes_table = sa.Table('episodes', metadata,
    sa.Column('ix', sa.Integer, primary_key=True),
    sa.Column('show_name', sa.Integer, sa.ForeignKey('shows.name')),
    sa.Column('name', sa.Unicode),
    sa.Column('season', sa.Integer),
    sa.Column('episode', sa.Integer),
    sa.Column('date', sa.DateTime()),
    sa.Column('group', sa.Unicode),
    sa.Column('torrent_hash', sa.String),
)

episode_qualities = sa.Table('episode_qualities', metadata,
    sa.Column('episode', sa.Integer, sa.ForeignKey('episodes.ix'), nullable=False),
    sa.Column('quality', sa.Integer, sa.ForeignKey('qualities.name'), nullable=False),
)

class Show(object):
    def __init__(self, name):
        self.name = name
    
    def __repr__(self):
        return '<Show "%s">' % (self.name)

class Episode(object):
    def __init__(self, show, **kwargs):
        self.show = show
        if 'season' and 'episode' in kwargs:
            self.season = kwargs['season']
            self.episode = kwargs['episode']
        if 'date'  in kwargs:
            self.date = kwargs['date']
        if 'name'  in kwargs:
            self.name = kwargs['name']
        if 'group'  in kwargs:
            self.group = kwargs['group']
        if 'quality'  in kwargs:
            quality = kwargs['quality']
            qualities = []
            if isinstance(quality, Quality):
                qualities.append(quality)
            if isinstance(quality, list):
                qualities = quality
            self.quality = qualities
        if 'torrent_hash'  in kwargs:
            self.torrent_hash = kwargs['torrent_hash']
    
    def __repr__(self):
        out = '<Episode "%s"' % (self.show.name)
        if self.name:
            out += ' "%s"' % (self.name)
        if self.season and self.episode:
            out += ' %dx%d' % (self.season, self.episode)
        elif self.date:
            out += ' %s' % (self.date)
        out += ' %d' % (self.total_score())
        if self.group:
            out += ' %s' % (self.group)
        out += '>'
        return out
    
    def total_score(self):
        return Quality.total_score(self.quality)

class Quality(object):
    def __init__(self, name, score=0):
        self.name = name
        self.score = score
    
    def __repr__(self):
        return '<Quality "%s" %d>' % (self.name, self.score)
    
    @classmethod
    def total_score(self, qualities):
        score = 0
        for q in qualities:
            if isinstance(q, Quality):
                score += q.score
        return score

orm.mapper(Show, shows_table)
orm.mapper(Episode, episodes_table, properties={
    'quality': orm.relation(Quality, secondary=episode_qualities),
    'show': orm.relation(Show, backref=orm.backref('episodes')),
})
orm.mapper(Quality, qualities_table)
