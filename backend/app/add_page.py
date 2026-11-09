import os
import requests
import textwrap
import re
from dotenv import load_dotenv

load_dotenv()

class WikiManager:
    def __init__(self):
        self.api_url = "https://proton.snu.ac.kr/graphql"
        self.api_token = os.getenv("WIKI_API_TOKEN")
        if not self.api_token:
            raise Exception("WIKI_API_TOKEN environment variable is not set")
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_token}"
        }

    def dedent_content(self, content):
        """Removes leading spaces from multi-line strings while maintaining formatting."""
        return textwrap.dedent(content).strip()

    def create_page(self, data):
        """Create a new page in Wiki.js."""
        target = data.get('target')
        title = f"{target}"
        path = f"/ToO/{target.replace(' ', '')}"
        
        raw_content = f"""
        # {target}
        This is a requested ToO target.

        ## Request information
        """
        
        content = self.dedent_content(raw_content) + self.email_content(data)
        description = ""

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

        json_data = {
            "query": query,
            "variables": {
                "title": title,
                "content": content,
                "description": description,
                "path": path
            }
        }

        response = requests.post(self.api_url, headers=self.headers, json=json_data)
        return self._handle_response(response)

    def get_page_content(self, path):
        """Fetch the content of a Wiki.js page."""
        query = """
        query GetPage($path: String!, $locale: String!) {
          page(path: $path, locale: $locale) {
            id
            title
            content
          }
        }
        """
        response = requests.post(self.api_url, headers=self.headers, json={"query": query, "variables": {"path": path, "locale": "en"}})
        data = response.json()

        if 'errors' in data:
            raise Exception(f"GraphQL error: {data['errors']}")
        
        return data['data']['page']

    def update_page_content(self, path, new_content, title):
        """Update the entire page content in Wiki.js."""
        query = """
        mutation UpdatePage($path: String!, $title: String!, $content: String!, $locale: String!) {
          pageUpdate(
            path: $path,
            locale: $locale,
            input: {
              title: $title,
              content: $content
            }
          ) {
            id
            title
            path
          }
        }
        """
        variables = {
            "path": path,
            "title": title,
            "content": new_content,
            "locale": "en"
        }

        response = requests.post(self.api_url, headers=self.headers, json={"query": query, "variables": variables})
        return self._handle_response(response)

    def append_text_to_section(self, path, section_title, new_text):
        """Append new text to an existing section."""
        page = self.get_page_content(path)
        content = page['content']

        pattern = rf"(## {section_title}\n)(.*?)(?=\n## |\Z)"
        match = re.search(pattern, content, flags=re.DOTALL)

        if match:
            updated_section = match.group(2).strip() + f"\n\n{new_text}"  
            updated_content = re.sub(pattern, rf"\1{updated_section}\n", content, flags=re.DOTALL)
        else:
            updated_content = content.strip() + f"\n\n## {section_title}\n{new_text}"

        return self.update_page_content(path, updated_content, page['title'])

    def replace_text_in_section(self, path, section_title, old_text, new_text):
        """Replace specific text inside a given section."""
        page = self.get_page_content(path)
        content = page['content']

        pattern = rf"(## {section_title}\n)(.*?)(?=\n## |\Z)"
        match = re.search(pattern, content, flags=re.DOTALL)

        if match:
            updated_section = match.group(2).replace(old_text, new_text)  # Replace only the specific text
            updated_content = re.sub(pattern, rf"\1{updated_section}\n", content, flags=re.DOTALL)
        else:
            raise Exception(f"Section '{section_title}' not found.")

        return self.update_page_content(path, updated_content, page['title'])

    def email_content(self, data):
        """Generate email content for the Wiki.js page."""
        obsmode = data.get('obsmode')

        if obsmode == "Spec":
            details1 = f"- Specmode: {data.get('selectedSpecFile')}"
            details2 = ""
        elif obsmode == "Deep":
            selected_filters = ",".join(list(data.get('selectedFilters')))
            details1 = f"- Filters: {selected_filters}"
            details2 = f"- Number of Telescopes: {data.get('selectedTelNumber')}"

        data["singleExposure"] = data.get('exposure')
        data["exposure"] = float(data.get('singleExposure')) * float(data.get('imageCount'))

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
        return self.dedent_content(email_body)

    def _handle_response(self, response):
        """Handle API responses."""
        if response.status_code != 200:
            error_msg = f"HTTP Error: {response.status_code}"
            try:
                error_detail = response.text
                error_msg += f" - {error_detail}"
            except:
                pass
            print(error_msg)
            raise Exception(error_msg)

        try:
            result = response.json()
        except Exception as e:
            error_msg = f"Failed to parse JSON response: {str(e)}"
            print(error_msg)
            raise Exception(error_msg)
            
        if 'errors' in result:
            error_msg = f"GraphQL Error: {result['errors'][0]['message']}"
            if len(result['errors']) > 1:
                error_msg += f" (and {len(result['errors'])-1} more errors)"
            print(error_msg)
            raise Exception(error_msg)
        
        return result
