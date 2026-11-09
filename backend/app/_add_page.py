import os
import requests
import textwrap
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://proton.snu.ac.kr/graphql"
API_TOKEN = os.getenv("WIKI_API_TOKEN")

def dedent_content(content):
    """Removes leading spaces from multi-line strings while maintaining formatting."""
    return textwrap.dedent(content).strip()

def create_wiki_page(data):
    """
    Create a new page in Wiki.js
    """

    target = data.get('target')
    title = f"{target}"
    path = f"/ToO/{target.replace(' ', '')}"
    
    raw_content = f"""
    # {target}
    This is a requested ToO target.

    ## Request information

    """
    
    content = dedent_content(raw_content)
    content += email_content(data)

    description = ""

    # Set up API endpoint and headers
    api_endpoint = f"{API_URL}/graphql"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_TOKEN}"
    }
    
    # GraphQL mutation for creating a page
    query = """
    mutation ($title: String!, $content: String!, $description: String!, $path: String!) {
      pages {
        create(
          content: $content
          description: $description
          editor: "markdown"
          isPublished: true
          locale: "en"
          path: $path
          title: $title
          isPrivate: false
          tags: ["ToO"]
        ) {
          responseResult {
            succeeded
            message
          }
        }
      }
    }
    """

    # Data to send
    json_data = {
        "query": query,
        "variables": {
            "title": title,
            "content": content,
            "description": description,
            "path": path,            
        }
    }
    
    # Send request
    response = requests.post(api_endpoint, headers=headers, json=json_data)
    result = response.json()
    
    # Check result
    if 'errors' in result:
        print(f"Error: {result['errors'][0]['message']}")
    else:
        response_result = result['data']['pages']['create']['responseResult']
        if response_result['succeeded']:
            print(f"Page created successfully at: {path}")
        else:
            print(f"Failed to create page: {response_result['message']}")

def email_content(data):
    obsmode = data.get('obsmode')

    if obsmode == "Spec":
        details1 = f"- Specmode: {data.get('selectedSpecFile')}"
        details2 = ""
    elif obsmode == "Deep":
        selected_filters = ",".join(list(data.get('selectedFilters')))
        details1 = f"- Filters: {selected_filters}"
        details2 = f"- NumberofTelescopes: {data.get('selectedTelNumber')}"


    # Construct the email body
    data["singleExposure"] = data.get('exposure')
    data["exposure"] = float(data.get('singleExposure'))*float(data.get('imageCount'))

    target = data.get('target')

    email_body = f"""
>### Observation Information
> Requester: {data.get('requester')}
> Target Name: {data.get('target')}
> Right Ascension (R.A.): {data.get('ra')}
> Declination (Dec.): {data.get('dec')}
> Total Exposure Time (seconds): {data.get('exposure')}
> Single Exposure Time (seconds): {data.get('singleExposure')}
> Number of images: {data.get('imageCount')}
> Obsmode: {obsmode}
>    {details1}
>    {details2}
>
>### Detailed Settings
> Abort Current Observation: {data.get('abortObservation')}
> Priority: {data.get('priority')}
> Gain: {data.get('gain')}
> Radius (arcmin): {data.get('radius')}
> Binning: {data.get('binning')}
> Observation Start Time: {data.get('obsStartTime')}
> Comments: {data.get('comments')}
{{.is-info}}

## 7DT observation

## GCN reports from others
"""
    return email_body