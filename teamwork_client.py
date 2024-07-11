import requests
import base64

class TeamworkClient:

    def __init__(self, url, api_key):
        self.url = url
        self.api_key = api_key

        base64Auth = base64.b64encode(f"{self.api_key}:1".encode('utf-8')).decode("ascii")
        self.header = {
            'access-control-expose-headers': 'id,x-page',
            'Authorization': f'Basic {base64Auth}'
        }
    
    def get_projects(self, query_param=None):
        url = f"{self.url}/projects/api/v3/projects.json"
        response = requests.get(url=url, headers=self.header, params=query_param)
        return response
    
    def get_tasks_list(self, projectId, query_param=None):
        url = f"{self.url}/projects/api/v3/projects/{projectId}/tasklists"
        response = requests.get(url=url, headers=self.header, params=query_param)
        return response        
    
    def get_tasks(self, query_param=None):
        url = f"{self.url}/projects/api/v3/tasks.json"
        response = requests.get(url=url, headers=self.header, params=query_param)
        return response
    
    def get_tasks_from_tasks_list(self, tasklistId,query_param=None):
        url = f"{self.url}/projects/api/v3/tasklists/{tasklistId}/tasks.json"
        response = requests.get(url=url, headers=self.header, params=query_param)
        return response
    
    def post_time_entry_from_task(self, taskId, timeLog):
        url = f"{self.url}/projects/api/v3/tasks/{taskId}/time.json"
        response = requests.post(url=url, headers=self.header, json=timeLog)
        return response   

