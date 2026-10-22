import requests
import json


def search_github(query, num_results=5, search_type="repositories"):
    """
    使用 GitHub API 搜索代码或仓库。
    参数:
        query: 搜索关键词
        num_results: 返回结果数量，默认5
        search_type: 搜索类型，"repositories" 或 "code"
    返回:
        搜索结果列表
    """
    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'YukiV6-Skill'
    }
    
    if search_type == "code":
        url = f'https://api.github.com/search/code?q={query}&per_page={num_results}'
    else:
        url = f'https://api.github.com/search/repositories?q={query}&sort=stars&order=desc&per_page={num_results}'
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        results = []
        if data['total_count'] > 0:
            for item in data['items'][:num_results]:
                if search_type == "code":
                    results.append({
                        'repository': item['repository']['full_name'],
                        'path': item['path'],
                        'url': item['html_url']
                    })
                else:
                    results.append({
                        'name': item['full_name'],
                        'description': item.get('description', ''),
                        'stars': item['stargazers_count'],
                        'url': item['html_url']
                    })
        
        return results
    except Exception as e:
        return [{'error': str(e)}]


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("用法: python search_github.py <query> [num_results] [type]")
        print("type: repositories (默认) 或 code")
        sys.exit(1)
    
    query = sys.argv[1]
    num = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    search_type = sys.argv[3] if len(sys.argv) > 3 else "repositories"
    results = search_github(query, num, search_type)
    print(json.dumps(results, ensure_ascii=False, indent=2))