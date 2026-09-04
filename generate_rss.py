#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
明倫国際法律事務所 コラム RSSフィード生成スクリプト
毎週金曜日14:30（中国時間）に実行され、最新のコラム記事からRSSフィードを生成します。
"""

import os
import sys
import re
import ssl
import urllib3
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

# SSL警告を無効化（自己署名証明書対応）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 設定
BASE_URL = "https://www.meilin-law.jp"
COLUMN_URL = "https://www.meilin-law.jp/column/"
OUTPUT_FILE = "rss.xml"
MAX_ARTICLES = 25  # フィードに含める最大記事数

# 中国時間（UTC+8）のタイムゾーン
CHINA_TZ = timezone(timedelta(hours=8))

# セッションを作成（SSL検証を無効化）
session = requests.Session()
session.verify = False


def get_current_time_china():
    """現在時刻を中国時間（UTC+8）で取得"""
    return datetime.now(CHINA_TZ)


def parse_date(date_str):
    """
    日付文字列をパースしてdatetimeオブジェクトを返す
    例: "2026.08.25" -> datetime(2026, 8, 25)
    """
    try:
        # 年月日を抽出 (例: "2026.08.25" または "2026.08.25 など")
        match = re.search(r'(\d{4})\.(\d{2})\.(\d{2})', date_str)
        if match:
            year, month, day = map(int, match.groups())
            return datetime(year, month, day, tzinfo=CHINA_TZ)
    except Exception as e:
        print(f"日付パースエラー: {date_str} - {e}")
    return None


def fetch_articles():
    """
    コラム一覧ページから記事を取得する
    戻り値: 記事情報のリスト [{'title': ..., 'link': ..., 'date': ..., 'category': ..., 'description': ...}]
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
        'Connection': 'keep-alive',
    }
    
    try:
        # SSL検証を無効化してリクエスト
        response = session.get(COLUMN_URL, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        # ステータスコードとコンテンツの一部をログ出力（デバッグ用）
        print(f"ステータスコード: {response.status_code}")
        print(f"コンテンツサイズ: {len(response.text)} バイト")
        
    except requests.exceptions.SSLError as e:
        print(f"SSLエラーが発生しましたが、処理を続行します: {e}")
        # さらに強力なSSL無効化オプション
        try:
            # SSLコンテキストを作成して検証を完全に無効化
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            response = session.get(COLUMN_URL, headers=headers, timeout=30, verify=False)
            response.raise_for_status()
            response.encoding = 'utf-8'
            print(f"代替方法で接続成功: ステータスコード {response.status_code}")
        except Exception as e2:
            print(f"代替接続も失敗: {e2}")
            return []
            
    except requests.RequestException as e:
        print(f"ページ取得エラー: {e}")
        return []

    # BeautifulSoupでパース
    soup = BeautifulSoup(response.text, 'html.parser')
    articles = []

    # 記事リストの要素を取得（複数のセレクタを試行）
    article_items = soup.select('.list_clm li')
    
    if not article_items:
        # 代替セレクタを試す
        article_items = soup.select('.list_clm > li')
        
    if not article_items:
        # さらに別のセレクタを試す
        article_items = soup.select('.list_clm .col-md-6')
        
    if not article_items:
        # 記事が見つからない場合のデバッグ情報
        print("記事が見つかりませんでした。HTML構造を確認します。")
        # クラス名を含む要素を探す
        list_clm = soup.select('.list_clm')
        if list_clm:
            print(f".list_clm が見つかりました: {len(list_clm)} 個")
            # list_clm内のli要素を探す
            for elem in list_clm:
                items = elem.find_all('li')
                if items:
                    print(f"li要素が見つかりました: {len(items)} 個")
                    article_items = items
                    break
        else:
            print(".list_clm が見つかりませんでした。")
            # すべてのli要素を探す（フォールバック）
            all_li = soup.find_all('li')
            print(f"ページ内の全li要素数: {len(all_li)}")
            # 記事っぽいli要素をフィルタリング
            for li in all_li:
                if li.find('h3') and li.find('a'):
                    article_items.append(li)
            print(f"記事候補のli要素: {len(article_items)} 個")
    
    if not article_items:
        print("記事が見つかりませんでした。HTML構造が変更されている可能性があります。")
        return []

    print(f"{len(article_items)}件の記事候補が見つかりました。")
    
    for idx, item in enumerate(article_items[:MAX_ARTICLES]):
        try:
            link_elem = item.find('a')
            if not link_elem:
                continue
                
            link = urljoin(BASE_URL, link_elem.get('href', ''))
            
            # タイトル
            title_elem = link_elem.find('h3', class_='ttl')
            if not title_elem:
                # 代替: h3タグを探す
                title_elem = link_elem.find('h3')
            title = title_elem.get_text(strip=True) if title_elem else "タイトルなし"
            
            # 日付
            date_elem = item.find('p', class_='date')
            if not date_elem:
                # 代替: 日付っぽいテキストを探す
                for elem in item.find_all(['p', 'span', 'div']):
                    if re.search(r'\d{4}\.\d{2}\.\d{2}', elem.get_text()):
                        date_elem = elem
                        break
            date_str = date_elem.get_text(strip=True) if date_elem else ""
            pub_date = parse_date(date_str)
            
            # カテゴリー
            category_elem = item.find('p', class_='cate')
            if not category_elem:
                # 代替: カテゴリーっぽいテキストを探す
                for elem in item.find_all(['p', 'span', 'div']):
                    text = elem.get_text(strip=True)
                    if text and len(text) < 20 and not re.search(r'\d', text):
                        category_elem = elem
                        break
            category = category_elem.get_text(strip=True) if category_elem else ""
            
            # 説明（本文の抜粋）
            desc_elem = item.find('p', class_='txt')
            if not desc_elem:
                # 代替: 説明っぽいテキストを探す
                for elem in item.find_all(['p', 'div']):
                    text = elem.get_text(strip=True)
                    if len(text) > 50 and '執筆者' in text:
                        desc_elem = elem
                        break
            description = desc_elem.get_text(strip=True) if desc_elem else ""
            
            articles.append({
                'title': title,
                'link': link,
                'date': pub_date,
                'category': category,
                'description': description,
            })
            
            print(f"  {idx+1}. {title[:30]}... ({date_str})")
            
        except Exception as e:
            print(f"記事 {idx+1} の解析中にエラー: {e}")
            continue

    return articles


def generate_rss(articles):
    """
    記事リストからRSSフィードを生成する
    """
    if not articles:
        print("記事がありません。RSSフィードを生成できません。")
        return None

    fg = FeedGenerator()
    fg.title('明倫国際法律事務所 コラム')
    fg.link(href='https://www.meilin-law.jp/column/', rel='alternate')
    fg.link(href='https://www.meilin-law.jp/rss.xml', rel='self')
    fg.description('明倫国際法律事務所のコラム記事一覧です。')
    fg.language('ja')
    
    # サイトの最終更新日時を設定（最新記事の日付を使用）
    latest_date = None
    for article in articles:
        if article['date']:
            if latest_date is None or article['date'] > latest_date:
                latest_date = article['date']
    
    if latest_date:
        fg.lastBuildDate(latest_date)
    
    # 各記事をフィードに追加
    for article in articles:
        entry = fg.add_entry()
        entry.title(article['title'])
        entry.link(href=article['link'])
        
        if article['date']:
            entry.pubDate(article['date'])
            entry.updated(article['date'])
        
        if article['category']:
            entry.category(term=article['category'])
        
        # 説明文の生成
        description_parts = []
        if article['category']:
            description_parts.append(f"カテゴリー: {article['category']}")
        if article['description']:
            description_parts.append(article['description'])
        
        description = "\n".join(description_parts)
        entry.description(description)
        entry.content(description, type='text/plain')

    return fg


def main():
    """メイン関数"""
    print(f"=== RSSフィード生成開始 ({get_current_time_china().isoformat()}) ===")
    
    # 記事を取得
    print("コラム記事を取得中...")
    articles = fetch_articles()
    print(f"{len(articles)}件の記事を取得しました。")
    
    if not articles:
        print("記事が取得できなかったため、RSSフィードを生成しません。")
        sys.exit(1)
    
    # RSSフィードを生成
    print("RSSフィードを生成中...")
    feed = generate_rss(articles)
    
    if feed is None:
        print("RSSフィードの生成に失敗しました。")
        sys.exit(1)
    
    # RSSをファイルに出力
    try:
        rss_str = feed.rss_str(pretty=True)
        with open(OUTPUT_FILE, 'wb') as f:
            f.write(rss_str)
        print(f"RSSフィードを {OUTPUT_FILE} に出力しました。")
        print(f"総記事数: {len(articles)}件")
    except Exception as e:
        print(f"ファイル出力エラー: {e}")
        sys.exit(1)
    
    print("=== RSSフィード生成完了 ===")


if __name__ == "__main__":
    main()
