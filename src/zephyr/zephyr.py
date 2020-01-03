''' ZEPHYR for JIRA Client
    A python client for the Zephyr for Jira plugin from SmartBear.
    Official API documentation is NOT reliable, but can be found here:
    https://getzephyr.docs.apiary.io
'''
from typing import List
from requests import Session
import jira
from resources import (Project,
                       Folder,
                       Execution)
from config import (SERVER,
                    USER,
                    PASSWORD,
                    VERIFY,
                    TIMEOUT)

_HEADERS = {"Content-Type": "application/json"}
ZAPI_URL = '{}/rest/zapi/latest/'
EMPTY_CYCLES_REQUEST = ZAPI_URL + 'cycle?expand='

EXECUTIONS_URL = ZAPI_URL + 'execution/?projectId={}&versionId={}&cycleId={}&folderId={}'
EXECUTIONS_ZQL_URL = ZAPI_URL + 'zql/executeSearch?zqlQuery={}'
MOVE_EXEUCTIONS_URL = ZAPI_URL + 'cycle/{}/move/executions/folder/{}'

ERROR_DESC = 'errorDesc'

class Zephyr():
    """Client session that leverages a requests.Session to interface with the Zephyr API
    """
    def __init__(self,
                 server=SERVER,
                 basic_auth=None,
                 verify: bool = VERIFY,
                 timeout: int = TIMEOUT):
        self.server: str = server  #TODO: this isn't actually read.  SERVER from configs is used for all the URLs.  Fix it quick.
        self.timeout = timeout
        self._session = Session()
        self._session.headers.update(_HEADERS)
        if basic_auth:
            self._session.auth = basic_auth
        else:
            self._session.auth = (USER, PASSWORD)
        self._session.verify = verify
        self._projects = None  # assign None for uninitialized state
        self._check_connection()

    @property
    def projects(self):
        """Lazily loaded projects property

        Returns:
            List[Project]:
        """
        if self._projects is None:
            self._load_projects()
        return self._projects

    def _load_projects(self):
        """Loads a list of projects using the jira library.  ZAPI responses are not suitable, as they do not
        contain key names.  See documentation for project loading here: 
        https://getzephyr.docs.apiary.io/#reference/utilresource/get-all-projects/get-all-projects
        Response data example is NOT provided, but when calls were made to a real server, project name was not
        present.
        """
        jira_session = jira.JIRA(server=self.server, auth=self._session.auth, timeout=self.timeout)
        projects = jira_session.projects()
        projects = [Project(name=x.key,
                            id_=x.id,
                            session=self._session) for x in projects]
        self._projects = projects
        jira_session.close()

    def project(self, name):
        """Find project by name (also known as key), not by integer id

        Args:
            name (str)

        Returns:
            Project
        """
        proj, = [x for x in self.projects if x.name == name]
        return proj

    def executions_zql(self, query: str):
        """Search for executions using ZQL

        Args:
            query (str): ZQL query

        Returns:
            List[Execution]
        """
        url = EXECUTIONS_ZQL_URL.format(self.server, query)
        response = self.get(url=url)
        return response.json()

    def get(self, url, params=None):
        response = self._session.get(url=url, params=params, timeout=self.timeout)
        jira.resilientsession.raise_on_error(response)
        error = response.json().get(ERROR_DESC)
        if error:
            raise jira.JIRAError

    def put(self, url, data):
        return self._session.put(url=url, data=data, timeout=self.timeout)

    def move_executions(self, executions: List[Execution], folder: Folder):
        url = MOVE_EXEUCTIONS_URL.format(folder.cycle, folder.id_)
        executions = [x.id for x in executions]
        payload = {'projectId': folder.project,
                   'versionId': folder.version,
                   'schedulesList': executions}
        response = self.put(url, data=payload)
        if response.status_code != 200:
            raise jira.JIRAError(response=response)

    def _check_connection(self):
        """Verify connection to ZAPI server (called on init)

        Raises:
            ValueError: If server responds, but authentication failed
            ConnectionError: If no parseable response from server
        """
        url = EMPTY_CYCLES_REQUEST.format(self.server)
        response = self.get(url)
        jira.resilientsession.raise_on_error(response)

    def _test_spam_calls(self, calls=200):
        failed_responses = []
        project_id = 10204
        version_id = 20418
        cycle_id = 3447
        folder_id = 330
        url = EXECUTIONS_URL.format(self.server, project_id, version_id, cycle_id, folder_id)
        for _ in range(calls):
            response = self.get(url)
            if response.status_code != 200:
                failed_responses.append(response.content)
        if failed_responses:
            print("Failed calls: %s" % len(failed_responses))

    def raise_on_error(self, response):
        """If auth=None, the Zephyr API responds with a 200 status and the following content:
            {
             'errorDesc':'You do not have the permission to make this request. Login Required.',
             'errorId': 'ERROR'
            }
        due to this, additional handling has been added to the jira client's raise_on_error method.
        Invalid auth credentials will generate the expected 401 error

        Arguments:
            response {requests.Response}
        """
        if response.status_code == 200 and ERROR_DESC in response.content:
            response.status_code = 401  # edit status code on the fly so jira lib method handles it
        jira.resilientsession.raise_on_error(response)
