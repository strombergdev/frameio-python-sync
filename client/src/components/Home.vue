<template>
  <div class="container">
    <div class="row">
      <div class="col-sm-10">
        <div class="row d-flex justify-content-between">
          <h3>FRAME.IO FOLDER SYNC</h3>
          <div style="margin-top: 5px;">
            <div v-if="!logged_in">
              <button
                type="button"
                class="btn btn-primary btn-sm"
                @click="login"
              >LOGIN</button>
              <button
                v-b-modal.dev-token-modal
                type="button"
                class="btn btn-primary btn-sm"
                style="margin-top: 15px; margin-bottom: 15px; margin-left: 5px;"
              >DEV TOKEN LOGIN</button>
            </div>
            <div v-else>
              <button
                type="button"
                class="btn btn-primary btn-sm"
                @click="logout"
              >LOGOUT</button>
            </div>
          </div>
        </div>
        <hr>
        <b-alert
          :show="dismissCountDown"
          dismissible
          :variant="alertType"
          @dismissed="dismissCountDown = 0"
          @dismiss-count-down="countDownChanged"
        >{{ alertMessage }}</b-alert>
        <div v-if="logged_in && teamID !== ''">
          <div>
            <h6 class="title">TEAM</h6>
            <select
              v-model="selectedTeam"
              class="form-control"
              @change="selectTeam($event)"
            >
              <option
                v-for="team in teams"
                :key="team.id"
                :value="team.id"
              >{{ team.name }}</option>
            </select>
          </div>
          <button
            v-b-modal.update-ignoreFolders-modal
            style="margin-top: 15px; margin-bottom: 15px;"
            type="button"
            class="btn btn-primary btn-sm"
          >IGNORE FOLDERS</button>
          <button
            v-b-modal.log-modal
            class="btn btn-primary btn-sm"
            style="margin-top: 15px; margin-bottom: 15px; margin-left: 5px;"
          >LOG</button>
          <table class="table table-hover">
            <thead>
              <tr>
                <th
                  class="title"
                  scope="col"
                >PROJECT</th>
                <th
                  class="title"
                  scope="col"
                >LOCAL FOLDER</th>
                <th />
                <th
                  class="title"
                  scope="col"
                >SYNC?</th>

              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(project, index) in activeProjects"
                :key="index"
              >
                <td>{{ project.name }}</td>
                <td>{{ project.local_path }}</td>
                <td>
                  <div
                    class="btn-group"
                    role="group"
                  >
                    <button
                      v-b-modal.update-syncFolder-modal
                      style="color: white;"
                      type="button"
                      class="btn btn-primary btn-sm"
                      @click="editproject(project)"
                    >SELECT FOLDER</button>
                  </div>
                </td>
                <td v-if="project.local_path === 'Not set'">
                  <toggle-button
                    v-model="project.sync"
                    disabled
                    color="#5a52ff"
                    @change="toggleSync(project.id, project.sync)"
                  />
                </td>
                <td v-else>
                  <toggle-button
                    v-model="project.sync"
                    color="#5a52ff"
                    @change="toggleSync(project.id, project.sync)"
                  />
                </td>

              </tr>
            </tbody>
          </table>
          <table
            v-if="deletedProjects.length !== 0"
            style="margin-top: 20px;"
            class="table table-hover"
          >
            <thead>
              <tr>
                <th
                  class="title"
                  scope="col"
                >DELETED PROJECTS</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(project, index) in deletedProjects"
                :key="index"
              >
                <td>{{ project.name }}
                  <button
                    style="color: white; margin-left:10px;"
                    type="button"
                    class="btn btn-primary btn-sm"
                    @click="removeOldProject(project)"
                  >X</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
    <div>
      <b-modal
        id="dev-token-modal"
        title="Dev token login"
        hide-footer
      >
        <input
          id="devTokenInput"
          v-model="devToken"
          type="title"
          class="form-control"
          placeholder="Dev token"
        >
        <b-button
          type="submit"
          variant="primary"
          style="margin-top: 15px;"
          @click="devTokenLogin"
        >Login</b-button>
      </b-modal>
    </div>
    <div>
      <b-modal
        id="log-modal"
        size="xl"
        title="Log"
        hide-footer
        @shown="startLogPoll()"
        @hidden="stopLogPoll()"
      >
        <h6>
          Please close this window when done to save system resources</h6>
        <virtual-list
          ref="vsl"
          class="list scroll-touch"
          :data-key="'id'"
          :data-sources="latestLogs"
          :data-component="itemComponent"
          :estimate-size="500"
          :item-class="'list-item-fixed'"
        />
        <button
          v-if="scroll"
          type="button"
          class="btn btn-primary btn-sm"
          style="margin-top: 15px;"
          @click="stopLogPoll()"
        >Disable auto update</button>
        <button
          v-else
          type="button"
          style="margin-top: 15px;"
          class="btn btn-primary btn-sm"
          @click="startLogPoll()"
        >Enable auto update</button></b-modal>
    </div>

    <b-modal
      id="update-syncFolder-modal"
      ref="updateSyncFolderModal"
      size="xl"
      name="Update"
      hide-footer
      title="Select folder"
    >
      <b-form
        class="w-100"
        @submit="onSubmitSyncFolder"
      >

        <v-jstree
          ref="folderUpdate"
          :data="syncFolderTree"
          :async="loadSyncFolderData"
          show-checkbox
          allow-batch
          whole-row
        />
        <label style="margin-top:10px;">Create subfolder</label>
        <input
          id="folderInput"
          v-model="subFolder"
          type="title"
          class="form-control col-4"
          placeholder="Optional"
        >
        <b-form-group id="form-read-edit-group" />
        <b-button-group>
          <b-button
            type="submit"
            variant="primary"
          >Save</b-button>
        </b-button-group>
      </b-form>
    </b-modal>
    <b-modal
      id="update-ignoreFolders-modal"
      ref="updateIgnoreFoldersModal"
      name="Update"
      hide-footer
      title="Ignore folders"
    >
      <h6
        style="margin-bottom: 15px;"
      >Add the name of the folder(s) you don't want synced</h6>
      <form>
        <input
          id="folderInput"
          v-model="newIgnoreFolder"
          type="title"
          class="form-control"
          placeholder="Folder name"
        >
        <button
          type="button"
          class="btn btn-primary btn-sm"
          style="margin-top: 7px;"
          @click="addIgnoreFolder(newIgnoreFolder)"
        >ADD</button>
      </form>
      <br>
      <table
        class="table table-hover"
      >
        <tbody>
          <tr
            v-for="(folder, index) in ignoreFolders"
            :key="index"
          >
            <td>{{ folder.name }}</td>
            <td>
              <button
                style="color: white;"
                type="button"
                class="btn btn-danger btn-sm"
                @click="removeIgnoreFolder(folder.name)"
              >X</button>
            </td>
          </tr>
        </tbody>
      </table>
      <b-form-group id="form-read-edit-group" />
    </b-modal>
  </div>
</template>

<script>
import VirtualList from 'vue-virtual-scroll-list';
import axios from 'axios';
import { ToggleButton } from 'vue-js-toggle-button';
import VJstree from 'vue-jstree';
import Item from './Item.vue';

const backendPort = 5111;
const backendURL = `http://${window.location.hostname}`;
const frameAuthURL = 'https://applications.frame.io/oauth2/auth?';
const pkceChallenge = require('pkce-challenge');

export default {
  components: {
    ToggleButton,
    VJstree,
    'virtual-list': VirtualList,
  },
  data() {
    return {
      subFolder: '',
      devToken: '',
      showModal: true,
      latestLogs: [],
      scroll: true,
      count: 0,
      itemComponent: Item,
      newIgnoreFolder: '',
      ignoreFolders: [],
      dismissSecs: 10,
      dismissCountDown: 0,
      selectedProject: '',
      syncFolderTree: [],
      currentPath: '/',
      selectedFolder: '',
      folders: [],
      selectedTeam: '',
      sync: true,
      logged_in: false,
      teamID: '',
      teams: [],
      projects: [],
      alertMessage: '',
      alertType: 'success',
      showMessage: false,
    };
  },
  computed: {
    activeProjects() {
      return this.projects.filter((project) => project.deleted === false);
    },
    deletedProjects() {
      return this.projects.filter((
        project,
      ) => project.deleted === true && project.db_delete_requested === false);
    },
  },
  async created() {
    await this.checkLoginStatus();

    if (localStorage.firstLogin === 'true') {
      this.alertMessage = 'Logged in! Please allow the server 1 min to get your Frame.io projects and then reload the page';
      this.alertType = 'success';
      this.showAlert();
      localStorage.firstLogin = 'false';
    }

    // Frame.io auth workflow
    if (this.$route.query.code) {
      await this.postCodeForToken(this.$route.query.code, this.$route.query.state);
    }

    if (this.logged_in) {
      this.teams = await this.getTeams();
      this.ignoreFolders = await this.getIgnoreFolders();
      if (!localStorage.team) {
        await this.getProjects(this.teams[0].id);
        this.selectedTeam = this.teams[0].id;
      } else {
        await this.getProjects(localStorage.team);
        this.selectedTeam = localStorage.team;
      }
      await this.getSubfolders(this.currentPath);
    }
  },
  methods: {
    async devTokenLogin() {
      this.$bvModal.hide('dev-token-modal');
      // Test if token works.
      const result = await fetch('https://api.frame.io/v2/me', {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${this.devToken}`,
        },
      });

      // Token valid
      if (result.status === 200) {
        await fetch(`${backendURL}:${backendPort}/api/devtokenlogin`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ token: this.devToken }),
        });
        localStorage.firstLogin = 'true';
        setTimeout(() => {
          window.location.replace('/');
        }, 300);
        // Token invalid
      } else if (result.status === 401) {
        this.alertMessage = 'Invalid token, please retry';
        this.alertType = 'danger';
        this.showAlert();
      }
    },
    startLogPoll() {
      this.scroll = true;
      this.pollData();
    },
    stopLogPoll() {
      this.scroll = false;
      clearInterval(this.polling);
    },
    async removeIgnoreFolder(folder) {
      const res = await axios({
        method: 'DELETE',
        url: `${backendURL}:${backendPort}/api/ignorefolders`,
        headers: { 'Content-Type': 'application/json' },
        data: { folder },
      });
      if (res.status === 200) {
        this.ignoreFolders = await this.getIgnoreFolders();
      }
    },
    async addIgnoreFolder(newFolder) {
      let found = false;
      this.ignoreFolders.forEach((folder) => {
        if (folder.name === newFolder) {
          found = true;
        }
      });
      if (newFolder === '') {
        found = true;
      }
      if (!found) {
        const res = await axios({
          method: 'PUT',
          url: `${backendURL}:${backendPort}/api/ignorefolders`,
          headers: { 'Content-Type': 'application/json' },
          data: { folder: newFolder },
        });
        if (res.status === 200) {
          this.ignoreFolders = await this.getIgnoreFolders();
        }
      }
      this.newIgnoreFolder = '';
    },
    async getIgnoreFolders() {
      try {
        const res = await axios({ url: `${backendURL}:${backendPort}/api/ignorefolders`, method: 'get' });
        if (res.status === 200) {
          const folders = res.data;
          folders.sort(this.compareObjects);
          return folders;
        }
      } catch (error) {
        console.error(error);
      }
      return null;
    },
    countDownChanged(dismissCountDown) {
      this.dismissCountDown = dismissCountDown;
    },
    showAlert() {
      this.dismissCountDown = this.dismissSecs;
    },
    async toggleSync(projectID, value) {
      const res = await axios({
        method: 'PUT',
        url: `${backendURL}:${backendPort}/api/projects/${projectID}`,
        headers: { 'Content-Type': 'application/json' },
        data: { sync: value },
      });
      if (res.status === 200) {
        this.alertMessage = 'Sync setting updated!';
        this.alertType = 'success';
        this.showAlert();
      } else {
        this.alertMessage = 'Sync update failed, try reloading.';
        this.alertType = 'danger';
        this.showAlert();
      }
    },
    async loadSyncFolderData(oriNode, resolve) {
      let data = [];
      if (oriNode.data.id === undefined) {
        data = await this.getSubfolders('/');
      } else {
        data = await this.getSubfolders(oriNode.data.text);
      }
      resolve(data);
    },
    async getSubfolders(currentPath) {
      const newFolders = [];
      try {
        const res = await axios({
          url: `${backendURL}:${backendPort}/api/folders`,
          method: 'post',
          data: { path: currentPath },
        });
        if (res.status === 200) {
          res.data.forEach((element) => {
            newFolders.push({ text: element, icon: 'fa fa-check icon-state-success' });
          });
        }
      } catch (error) {
        console.error(error);
      }
      return newFolders;
    },
    selectTeam(event) {
      this.selectedTeam = event.target.value;
      this.getProjects(this.selectedTeam);
      localStorage.team = this.selectedTeam;
    },
    async logout() {
      const res = await axios({ url: `${backendURL}:${backendPort}/api/logout`, method: 'post' });
      if (res.status === 200) {
        localStorage.removeItem('team');
        this.logged_in = false;
        window.location.replace('/');
      } else {
        console.log(res.status);
      }
    },
    login() {
      axios
        .get(`${backendURL}:${backendPort}/api/logindata`)
        .then((res) => {
          let authUrl = '';
          localStorage.state = pkceChallenge().code_challenge;

          const authParams = {
            response_type: 'code',
            redirect_uri: res.data.redirect_url,
            client_id: res.data.client_id,
            scope: res.data.scopes,
            state: localStorage.state,
          };

          Object.keys(authParams).forEach((key) => {
            if (authUrl !== '') {
              authUrl += '&';
            }
            authUrl += `${key}=${encodeURIComponent(authParams[key])}`;
          });
          authUrl = frameAuthURL + authUrl;
          setTimeout(() => {
            window.location.href = authUrl;
          }, 300);
        })
        .catch((error) => {
          console.error(error);
        });
    },
    compareObjects(a, b) {
      if (a.name.toUpperCase() < b.name.toUpperCase()) {
        return -1;
      }
      if (a.name.toUpperCase() > b.name.toUpperCase()) {
        return 1;
      }
      return 0;
    },
    async postCodeForToken(code, state) {
      if (localStorage.state === state) {
        await fetch(`${backendURL}:${backendPort}/api/tokenexchange`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ code, state }),
        });
        localStorage.firstLogin = 'true';
        setTimeout(() => {
          window.location.replace('/');
        }, 300);
      }
    },
    async getProjects(teamID) {
      axios
        .get(`${backendURL}:${backendPort}/api/${teamID}/projects`)
        .then((res) => {
          this.projects = res.data;
          this.projects.sort(this.compareObjects);
        })
        .catch((error) => {
          console.error(error);
        });
    },
    async getTeams() {
      try {
        const res = await axios({ url: `${backendURL}:${backendPort}/api/teams`, method: 'get' });
        if (res.status === 200) {
          const teams = res.data;
          teams.sort(this.compareObjects);
          return teams;
        }
      } catch (error) {
        console.error(error);
      }
      return null;
    },
    findSelectedFolder(folders) {
      folders.forEach((folder) => {
        if (folder.text.startsWith('/')) {
          if (folder.selected === true) {
            this.selectedFolder = folder.text;
          }
          this.findSelectedFolder(folder.children);
        }
      });
    },
    editproject(project) {
      this.selectedProject = project;
    },
    async onSubmitSyncFolder(evt) {
      this.findSelectedFolder(this.syncFolderTree);

      evt.preventDefault();
      this.$refs.updateSyncFolderModal.hide();

      axios
        .put(
          `${backendURL}:${backendPort}/api/projects/${this.selectedProject.id}`,
          { local_path: this.selectedFolder, sub_folder: this.subFolder },
          { headers: { 'Content-Type': 'application/json' } },
        )
        .then(() => {
          this.projects.forEach((project, i) => {
            if (project.id === this.selectedProject.id) {
              if (this.subFolder === '') {
                this.projects[i].local_path = this.selectedFolder;
              } else {
                this.projects[i].local_path = `${this.selectedFolder}/${this.subFolder}`;
              }
            }
          });
          this.subFolder = '';
          this.alertMessage = 'Path updated!';
          this.alertType = 'success';
          this.showAlert();
        })
        .catch(() => {
          this.alertMessage = 'Path update failed, do you have write permissions to this folder?';
          this.alertType = 'danger';
          this.showAlert();
        });
    },
    async checkLoginStatus() {
      try {
        const res = await axios({
          url: `${backendURL}:${backendPort}/api/loginstatus`,
          method: 'get',
        });
        if (res.status === 200) {
          this.logged_in = res.data.logged_in;
          this.teamID = res.data.team_id;
        }
      } catch (error) {
        this.alertMessage = 'Server unavailable, try restarting the app';
        this.alertType = 'danger';
        this.showAlert();
      }
    },
    setVirtualListToBottom() {
      if (this.$refs.vsl) {
        if (this.scroll) {
          this.$refs.vsl.scrollToBottom();
        }
      }
    },
    async getLatestLogs() {
      try {
        const res = await axios({ url: `${backendURL}:${backendPort}/api/log`, method: 'get' });
        if (res.status === 200) {
          const result = res.data;
          let count = 1;
          const logs = [];
          result.forEach((element) => {
            logs.push({
              name: element,
              id: count,
            });
            count += 1;
          });
          this.latestLogs = logs;
          this.setVirtualListToBottom();
        }
      } catch (error) {
        console.error(error);
      }
      return null;
    },
    pollData() {
      this.getLatestLogs();
      this.polling = setInterval(() => {
        this.getLatestLogs();
      }, 6000);
    },
    async removeOldProject(project) {
      try {
        const res = await axios({
          url: `${backendURL}:${backendPort}/api/${project.id}/remove`,
          method: 'post',
        });
        if (res.status === 200) {
          window.location.replace('/');
        }
      } catch (error) {
        console.error(error);
      }
    },
  },
};
</script>

<style>
.btn {
  background-color: #5a52ff;
  border-color: #5a52ff;
}

.title {
  font-size: 1rem;
  font-weight: bold;
}

</style>

<style lang="less">
.list {
  height: 700px;
  border: 1px solid;
  border-radius: 3px;
  overflow-y: auto;
  border-color:#DFDFDF;
  .list-item-fixed {
    display: flex;
    align-items: center;
    padding: 0 1em;
    height: 50px;
    border-bottom: 1px solid;
    border-color: lightgray;
  }
}
</style>
