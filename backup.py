# -*- coding:utf-8 -*-
import json
import requests
import datetime

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
        for channel in self.target_channel:
            members = self._get_slack_user_list(channel)
            user_list = self._make_member_dir(members)
            body_list = {}
            body = ''
            channel_name = self._get_slack_conversation_info(channel)
            message_list = self._get_slack_conversation_history(channel)
            print("message_list")
            print(len(message_list))
            count = 0
            for messages in message_list:
                for message in messages:
                    body += '\n' + '======'
                    if 'reply_count' in message:
                        reply_messages = self._get_slack_conversation_replys(channel, message['ts'])
                        for reply_message in reply_messages:
                            body = self._make_slack_body(reply_message, user_list, body)
                    else:
                        body = self._make_slack_body(message, user_list, body)
                count += 1
                print(count)
            body_list[channel_name] = body
        return body_list

    def _make_slack_body(self, message, user_list, body):
        time = message['ts'].split('.')
        if 'user' in message:
            user_id = message['user']
            post_info = str(datetime.datetime.fromtimestamp(int(time[0]))) + " " + user_list[user_id]
        else:
            post_info = str(datetime.datetime.fromtimestamp(int(time[0])))
        post_body = str(message['text'])
        if '```' in post_body:
            post_body = post_body.replace('```', '\n```\n')
        body += '\n' + post_info + '\n' + post_body
        return body

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
        for channel in request_message.keys():
            try:
                request_body = request_message[channel]
                if self.backup_period != 0:
                    oldest = datetime.datetime.now() - datetime.timedelta(days=self.backup_period)
                    period_path = oldest.strftime("%Y-%m-%d") + 'to' + datetime.datetime.today().strftime("%Y-%m-%d")
                else:
                    period_path = 'oldest' + 'to' + datetime.datetime.today().strftime("%Y-%m-%d")
                path = self.growi_article_path + channel + '-' + period_path
                url = self.growi_uri + '_api/pages.create'
                print(path)
                r = requests.post(url, data={'body': request_body, 'path': path, 'access_token': self.growi_token})
                print(r)
                print(r.json())
            except Exception as e:
                print('error')
                print(e)
        return

    def backup(self):
        '''
        メインルーチン
        実行すると、slackからメッセージ取得してgrowiに投稿するまで実行する
        設定ファイルとして、settings.jsonを使用する
        '''
        self._read_settings()
        request_messages = self._get_slack_channel()
        #self._post_growi(request_messages)

if __name__ == '__main__':
    aaa = SlackBackup()
    aaa.backup()