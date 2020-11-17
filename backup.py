# -*- coding:utf-8 -*-
import json
import requests
import datetime
import re

class SlackBackup():
    '''
    Slackからメッセージ取得してgrowiに記事としてバックアップを作成するプログラム
    '''
    def __init__(self):
        self.slack_token = ''
        self.growi_token = ''
        self.backup_period = 1
        self.limit = 20
        self.target_channel = []
        self.growi_article_path = ''
        self.growi_uri = ''

    def _read_settings(self):
        '''
        以下の設定を設定ファイルから取得
        - SlackおよびGrowiのトークン
        - 対象となるチャンネル
        - growiの記事作成先のパス
        - 取得期間(今から何日前までを取得するか)
        '''
        settings_file = open('settings.json', 'r')
        settings = json.load(settings_file)
        self.slack_token = settings['slack_token']
        self.growi_token = settings['growi_token']
        self.backup_period = settings['backup_period']
        self.limit = settings['limit']
        self.target_channel = settings['channel']
        self.growi_article_path = settings['growi_article_path']
        self.growi_uri = settings['growi_uri']
        return

    def _get_slack_channel(self):
        '''
        Slackにリクエスト送ってメッセージ一覧取得(時間指定なし(上限が10000件なのでlimit=10000なら全部取れる))
        '''
        channel_messsages = {}
        print('start ==get messages by slack==')
        for channel in self.target_channel:
            channel_name = self._get_slack_conversation_info(channel)
            print('channel {}'.format(channel_name))
            members = self._get_slack_user_list(channel)
            user_list = self._make_member_dir(members)
            message_list = self._get_slack_conversation_history(channel)
            body_list = []
            for messages in message_list:
                for message in messages:
                    post_list = []
                    body_messages = {}
                    message_time = message['ts'].split('.')
                    post_time = str(datetime.datetime.fromtimestamp(int(message_time[0])))
                    body_messages['post_time'] = post_time
                    if 'reply_count' in message:
                        body_messages['reply'] = True
                        reply_messages = self._get_slack_conversation_replys(channel, message['ts'])
                        for reply_message in reply_messages:
                            reply_post = {}
                            reply_post_time, reply_post_body = self._make_slack_body(reply_message, user_list)
                            reply_post['post_time'] = reply_post_time
                            reply_post['post_body'] = reply_post_body
                            post_list.append(reply_post)
                        body_messages['post'] = post_list
                    else:
                        body_messages['reply'] = False
                        _, post_body = self._make_slack_body(message, user_list)
                        body_messages['post'] = post_body
                    body_list.append(body_messages)
                body_list_sorted_by_time = sorted(body_list, key=lambda x: x['post_time'])
            channel_messsages[channel_name] = body_list_sorted_by_time
        print('end ==get messages by slack==')
        return channel_messsages

    def _make_slack_body(self, message, user_list):
        time = message['ts'].split('.')
        post_body = []
        post_time = str(datetime.datetime.fromtimestamp(int(time[0])))
        post_id = ""
        if 'user' in message:
            user_id = message['user']
            post_id = user_list[user_id]
        post_body.append(post_id)
        post_message = str(message['text'])
        if '```' in post_message:
            post_message = post_message.replace('```', '\n```\n')
        elif post_message == '':
            post_message = 'None'
        mention_list = re.findall(r'<@\w*>', post_message)
        if mention_list:
            for mention in mention_list:
                user_mention_id = re.search(r'\w+', mention).group()
                mention_user = user_list[user_mention_id]
                post_message = post_message.replace(mention, '@' + mention_user)
        post_body.append(post_message)
        return post_time, post_body

    def _get_slack_user_list(self, channel):
        '''
        slackのユーザのIDと名前を取得する
        '''
        url = 'https://slack.com/api/users.list'
        payload = {'token': self.slack_token}
        r = requests.get(url, params=payload)
        members = r.json()['members']
        return members

    def _make_member_dir(self, members):
        user_list = {}
        for member in members:
            if member["profile"]["display_name"] !="":
                user_list[member["id"]] = member["profile"]["display_name"]
            else:
                user_list[member["id"]] = member["profile"]["real_name"]
        return user_list

    def _get_slack_conversation_info(self, channel):
        '''
        slackのチャンネルの名前を取得する
        '''
        url = 'https://slack.com/api/conversations.info'
        payload = {'token': self.slack_token, 'channel': channel}
        r = requests.get(url, params=payload)
        messages = r.json()['channel']['name']
        return messages

    def _get_slack_conversation_history(self, channel):
        '''
        slackのチャンネルのメッセージ一覧を取得する(リプライは含まれない)
        '''
        message_list =[]
        url = 'https://slack.com/api/conversations.history'
        if self.backup_period == 0:
            oldest = 0
        else:
            oldest = (datetime.datetime.now() - datetime.timedelta(days=self.backup_period)).timestamp()
        payload = {'token': self.slack_token,'oldest': oldest, 'channel': channel, 'limit': self.limit}
        r = requests.get(url, params=payload)
        messages = r.json()['messages']
        message_list.append(messages)
        next_cursor = ''
        if 'response_metadata' in r.json():
            next_cursor = r.json()['response_metadata']['next_cursor']
        while next_cursor != '':
            payload = {'token': self.slack_token, 'channel': channel, 'oldest': oldest, 'limit': self.limit, 'cursor': next_cursor}
            r = requests.get(url, params=payload)
            messages = r.json()['messages']
            message_list.append(messages)
            if 'response_metadata' in r.json():
                next_cursor = r.json()['response_metadata']['next_cursor']
                continue
            else:
               break
        return message_list

    def _get_slack_conversation_replys(self, channel, time):
        '''
        slackのチャンネルのメッセージとそのリプライを取得する
        '''
        url = 'https://slack.com/api/conversations.replies'
        payload = {'token': self.slack_token, 'channel': channel, 'ts': time}
        r = requests.get(url, params=payload)
        messages = r.json()['messages']
        return messages

    def _post_growi(self, request_message):
        '''
        Growiに記事作成
        '''
        print('start ==post messages to growi==')
        for channel_name in request_message.keys():
            try:
                if self.backup_period != 0:
                    oldest = datetime.datetime.now() - datetime.timedelta(days=self.backup_period)
                    period_path = oldest.strftime("%Y-%m-%d") + 'to' + datetime.datetime.today().strftime("%Y-%m-%d")
                else:
                    period_path = 'oldest' + 'to' + datetime.datetime.today().strftime("%Y-%m-%d")
                request_body = self._post_body_growi(request_message[channel_name], period_path)
                path = self.growi_article_path + channel_name + '/' + period_path
                url = self.growi_uri + '_api/pages.create'
                r = requests.post(url, data={'body': request_body, 'path': path, 'access_token': self.growi_token})
                print(r)
                print(r.json())
            except Exception as e:
                print('error')
                print(e)
        print('end ==post messages to growi==')
        return

    def _post_body_growi(self, messages_list, title):
        '''
        Growi投稿用のメッセージ作成
        '''
        body = title + '\n'
        for message in messages_list:
            body += '======' + '\n'
            if message['reply']:
                for reply_message in message['post']:
                    body += reply_message['post_time'] + " " + reply_message['post_body'][0]
                    body += '\n'
                    body += reply_message['post_body'][1]
                    body += '\n'
            else:
                body += message['post_time']  + " " + message['post'][0]
                body += '\n'
                body += message['post'][1]
                body += '\n'
        body += '======'
        return body

    def backup(self):
        '''
        メインルーチン
        実行すると、slackからメッセージ取得してgrowiに投稿するまで実行する
        設定ファイルとして、settings.jsonを使用する
        '''
        self._read_settings()
        request_messages = self._get_slack_channel()
        self._post_growi(request_messages)

if __name__ == '__main__':
    slackbackup = SlackBackup()
    slackbackup.backup()