from datetime import datetime
import zipfile
import io
import ast
import re
import bcrypt


# Base Class for common attributes like ID, Name, Email, etc.
class Base:
    id_counter = 1
    
    def __init__(self, name, email, age=None):
        self.id = Base.id_counter  # Assign unique ID
        Base.id_counter += 1
        self.creation_date = datetime.now()  # Set the creation date
        self.name = name
        self.email = email
        self.age = age

    def display_info(self):
        return f"ID: {self.id}, Name: {self.name}, Email: {self.email}, Age: {self.age}, Created on: {self.creation_date}"

    def __repr__(self):
        return f"ID: {self.id}, Name: {self.name}, Email: {self.email}, Age: {self.age}"

# User Class (Inherits from Base)
class User(Base):
    def __init__(self, name, email, age, password=None, profile_photo=None):
        super().__init__(name, email, age)
        self.profile_photo = profile_photo
        self.blocked = False
        self.notifications = []
        self.password_hash = None  # Store hashed password

        if password:
            self.set_password(password)  # Set password during user creation
    
    def set_password(self, password):
        """Hash the password before storing it."""
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    
    def check_password(self, password):
        """Verify if the provided password matches the stored hash."""
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash)

    def login(self, password):
        """Login the user if the password matches."""
        if self.blocked:
            self.add_notification(f"{self.name} attempted to log in but is blocked.")
            return f"Login failed. {self.name} is blocked."
        
        if not self.check_password(password):
            self.add_notification(f"{self.name} attempted to log in with incorrect password.")
            return "Login failed. Incorrect password."

        return f"{self.name} logged in successfully."
    
    def display_info(self):
        info = super().display_info()
        if self.profile_photo:
            info += f", Profile Photo: {self.profile_photo}"
        else:
            info += ", No profile photo."
        return info

    def set_profile_photo(self, photo_path):
        self.profile_photo = photo_path
        return f"Profile photo updated to {photo_path}"

    def remove_profile_photo(self):
        self.profile_photo = None
        return "Profile photo removed."

    def block(self):
        """Block the user."""
        self.blocked = True
        self.add_notification(f"{self.name} has been blocked.")  # Add block notification
        return f"{self.name} has been blocked."
    
    def unblock(self):
        """Unblock the user."""
        if not self.blocked:
            return f"{self.name} is not blocked."
        self.blocked = False
        self.add_notification(f"{self.name} has been unblocked.")  # Add unblock notification
        return f"{self.name} has been unblocked."

    def add_notification(self, message):
        """Add a new notification for the user."""
        self.notifications.append(message)

    def view_notifications(self):
        """View all notifications for the user."""
        if not self.notifications:
            return f"No notifications for {self.name}."
        return "\n".join(self.notifications)

# Admin Class (Inherits from User)
class Admin(User):
    def __init__(self, name, email, age, role="Admin"):
        super().__init__(name, email, age)
        self.role = role
        self.reports = []  # List to store reports

    def post_user(self, app, name, email, age):
        """Admin can create a new user."""
        return app.post_user(name, email, age)

    def edit_user(self, app, user_index, new_email=None, new_age=None):
        """Admin can edit user details."""
        return app.edit_user(user_index, new_email, new_age)

    def delete_user(self, app, user_index):
        """Admin can delete a user."""
        return app.delete_user(user_index)

    def block_user(self, user):
        """Admin can block a user."""
        return user.block()

    def unblock_user(self, user):
        """Admin can unblock a user."""
        return user.unblock()

    def report_message(self, message, message_details):
        """Admin can review a reported message."""
        report = {
            "type": "message",
            "message": message.content,
            "details": message_details
        }
        self.reports.append(report)  # Add report to the admin's reports list
        return f"Message reported: {message.content}"

    def report_project(self, project, report_details):
        """Admin can review a reported project."""
        report = {
            "type": "project",
            "project": project.name,
            "details": report_details
        }
        self.reports.append(report)  # Add report to the admin's reports list
        return f"Project '{project.name}' reported."

    
# Message Class (Inherits from Base)
class Message(Base):
    def __init__(self, sender, content, timestamp=None):
        super().__init__(sender.name, sender.email, sender.age)
        self.sender = sender
        self.content = content
        self.timestamp = timestamp or datetime.now()
        self.likes = []  # List of users who liked this message

    def __repr__(self):
        return f"{self.timestamp} - {self.sender.name}: {self.content}"

    def like(self, user):
        """Allow a user to like this message."""
        if user not in self.likes:
            self.likes.append(user)  # Add user to the likes list
            # Notify the sender that their message was liked
            self.send_notification(self.sender, f"{user.name} liked your message: {self.content}")
            return f"{user.name} liked the message."
        else:
            return f"{user.name} has already liked this message."

    def unlike(self, user):
        """Allow a user to unlike this message."""
        if user in self.likes:
            self.likes.remove(user)  # Remove user from the likes list
            return f"{user.name} unliked the message."
        else:
            return f"{user.name} has not liked this message."

    def send_notification(self, user, message):
        """Send notification to the user."""
        user.add_notification(message)

# Thread Class (Inherits from Base)
class Thread(Base):
    def __init__(self, title, participants):
        super().__init__(participants[0].name, participants[0].email, participants[0].age)
        self.title = title  # Title of the thread
        self.participants = participants
        self.messages = []  # List of messages (Posts or Messages)

    def add_message(self, sender, content):
        # Create and store the new message
        new_message = Message(sender, content)
        self.messages.append(new_message)
        
        # Notify participants about the new message, excluding the sender
        for participant in self.participants:
            if participant != sender:
                notification_message = f"New message in thread '{self.title}' by {sender.name}: {content}"
                participant.add_notification(notification_message)
                                                
    def get_messages(self):
        return self.messages

    def like_message(self, message_index, user):
        """Like a message in the thread."""
        try:
            message = self.messages[message_index]
            return message.like(user)
        except IndexError:
            return "Message not found."

    def unlike_message(self, message_index, user):
        """Unlike a message in the thread."""
        try:
            message = self.messages[message_index]
            return message.unlike(user)
        except IndexError:
            return "Message not found."

# Forum Class to manage threads
class Forum:
    def __init__(self):
        self.threads = []

    def create_thread(self, title, participants, project):
        """Create a new thread in the forum and share a project."""
        new_thread = Thread(title, participants)
        self.threads.append(new_thread)

        # Notify participants about the shared project
        for participant in participants:
            participant.add_notification(f"The project '{project.name}' has been shared in the forum.")
        return new_thread

    def view_threads(self):
        """View all threads in the forum."""
        if not self.threads:
            return "No threads available."
        return "\n".join([f"Title: {thread.title}, Created by: {thread.participants[0].name}" for thread in self.threads])

    def get_thread(self, thread_index):
        """Get a specific thread's messages."""
        try:
            thread = self.threads[thread_index]
            return thread.get_messages()  # Return the list of messages in the thread
        except IndexError:
            return "Thread not found."

# App Class to handle users and forum
class App:
    def __init__(self):
        self.users = []
        self.projects = {}
        self.threads = []  # Public forum threads
        self.conversations = []  # Private user-to-user conversations
        self.files_in_memory = {}
        self.global_results = {'defined': [], 'called': {}}
        
    def get_users(self):
        if not self.users:
            return "No users found."
        return "\n".join([user.display_info() for user in self.users])

    def post_user(self, name, email, age):
        new_user = User(name, email, age)
        self.users.append(new_user)
        return f"User {name} added successfully."

    def create_thread(self, title, participants):
        """Create a new thread in the forum."""
        new_thread = Thread(title, participants)
        self.threads.append(new_thread)
        return new_thread

    def create_conversation(self, user1, user2):
        """Create a private conversation between two users."""
        # Check if the conversation already exists
        for conv in self.conversations:
            if {conv.user1, conv.user2} == {user1, user2}:  # Conversation already exists
                return conv
        
        # If conversation doesn't exist, create a new one
        conversation = Conversation(user1, user2)
        self.conversations.append(conversation)
        return conversation

    def send_private_message(self, sender, receiver, content):
        """Send a private message between two users."""
        # Find or create the conversation between sender and receiver
        conversation = None
        for conv in self.conversations:
            if {conv.user1, conv.user2} == {sender, receiver}:  # Check if conversation exists
                conversation = conv
                break
        if not conversation:
            conversation = self.create_conversation(sender, receiver)

        # Add message to the conversation
        conversation.add_message(sender, content)

    def like_message_in_thread(self, thread_index, message_index, user):
        """Like a message in a thread."""
        try:
            thread = self.threads[thread_index]
            message = thread.messages[message_index]
            result = message.like(user)
            return result
        except IndexError:
            return "Thread or message not found."

    def unlike_message_in_thread(self, thread_index, message_index, user):
        """Unlike a message in a thread."""
        try:
            thread = self.threads[thread_index]
            message = thread.messages[message_index]
            result = message.unlike(user)
            return result
        except IndexError:
            return "Thread or message not found."


    def like_message_in_conversation(self, conversation_index, message_index, user):
        """Like a message in a private conversation."""
        try:
            conversation = self.conversations[conversation_index]
            return conversation.like_message(message_index, user)
        except IndexError:
            return "Conversation or message not found."

    def unlike_message_in_conversation(self, conversation_index, message_index, user):
        """Unlike a message in a private conversation."""
        try:
            conversation = self.conversations[conversation_index]
            return conversation.unlike_message(message_index, user)
        except IndexError:
            return "Conversation or message not found."

    def create_project(self, name, description, creator):
        """Allow a user to create a project."""
        new_project = Project(name, description, creator)
        self.projects[name] = new_project  # Store the project
        creator.add_notification(f"The project '{name}' has been created.")  # Notify the creator only on project creation
        return new_project


    def edit_project(self, project, new_name, new_description):
        """Edit the name and description of an existing project."""
        project.name = new_name
        project.description = new_description

    def add_participant(self, project, user):
        """Add a user as a participant in the project."""
        if user not in project.participants:
            project.participants.append(user)
            user.add_notification(f"You have been added to the project '{project.name}' by {project.creator.name}.")
            project.creator.add_notification(f"{user.name} has been added to the project '{project.name}'.")

    def delete_project(self, project_name):
        """Delete a project from the list of projects."""
        if project_name in self.projects:
            project = self.projects[project_name]
            del self.projects[project_name]
            project.delete_project()  # Notify creator that the project was deleted
            return f"Project '{project_name}' deleted successfully."
        return f"Project '{project_name}' not found."
        
    def get_projects(self):
        """Return information about all projects."""
        if not self.projects:
            return "No projects available."
        return "\n".join([project.display_project_info() for project in self.projects])

    def display_all_projects(self):
        """Display all projects in a grouped format."""
        if not self.projects:
            return "No projects available."
        
        # Group the projects together in a formatted view
        project_info = "\n\n".join([f"Project {i+1}:\n{project.display_project_info()}" for i, project in enumerate(self.projects)])
        return f"--- All Projects ---\n{project_info}"

    def like_project(self, project_name, user):
        """Allow a user to like a project."""
        project = self.projects.get(project_name)
        if not project:
            return "Project not found."

        if user in project.liked_by:
            return f"{user.name} has already liked the project."

        project.liked_by.append(user)
        return f"{user.name} liked the project '{project_name}'."

    def unlike_project(self, project_name, user):
        """Allow a user to unlike a project."""
        project = self.projects.get(project_name)
        if not project:
            return "Project not found."

        if user not in project.liked_by:
            return f"{user.name} has not liked the project yet."

        project.liked_by.remove(user)
        return f"{user.name} unliked the project '{project_name}'."

    def consult_project(self, project_name, user):
        """Allow a user to consult another user's project."""
        project = self.projects.get(project_name)
        if not project:
            return "Project not found."

        # Display project details
        project_info = {
            "name": project.name,
            "description": project.description,
            "creator": project.creator.display_info(),
            "participants": [p.display_info() for p in project.participants]
        }

        return project_info

    def upload_zip(self, zip_file, project_name):
        """Upload and extract a zip file in memory, storing it in a Project object."""
        project = self.projects.get(project_name)
        if not project:
            return "Project not found."  # Handle case where project doesn't exist

        with zipfile.ZipFile(zip_file, 'r') as zip_ref:  # Use zip_file directly
            for file_name in zip_ref.namelist():
                with zip_ref.open(file_name) as file:
                    content = file.read().decode('utf-8')
                    project.add_file(file_name, content)

        return f"Files uploaded to project '{project_name}' successfully."

    def download_project(self, project_name):
        """Download a project as a zip file."""
        project = self.projects.get(project_name)
        if not project:
            return "Project not found."

        # Create a BytesIO object to store the zip file in memory
        zip_buffer = io.BytesIO()

        # Create a zip file in memory
        with zipfile.ZipFile(zip_buffer, 'w') as zipf:
            # Add each file in the project to the zip file
            for file_name, content in project.files.items():
                zipf.writestr(file_name, content)

        # Seek to the start of the BytesIO buffer
        zip_buffer.seek(0)

        return zip_buffer  # Return the zip file for downloading

    def add_participant(self, project, user):
        """Add a user as a participant in the project."""
        if user not in project.participants:
            project.participants.append(user)

    def remove_participant(self, project, user):
        """Remove a user as a participant in the project."""
        if user in project.participants:
            project.participants.remove(user)



    def parse_files(self, project_name):
        project = self.projects.get(project_name)
        if not project:
            return "Project not found."

        global_results = {
            "defined": [],
            "lambda_functions": [],
            "called": {},
            "comments": [],
            "html": {},
            "css": {},
            "js": {},
            # NEW:
            "edges": [],             # [{from:{file,func}, to:{file?,func}, line, kind}]
            "called_by": {},         # {func: [ {file, line, caller} ]}
            "imports_resolved": {},  # {file: [ {module, names, line, resolved_file} ]}
            "metrics": {},           # {file: {num_functions, num_calls, words}}
        }
        file_results = {}

        # pass 1 — parse all files, collect definitions, calls, imports
        py_parsers = {}
        js_parsers = {}
        c_parsers = {}

        for file_name, content in project.files.items():
            if file_name.endswith(".py"):
                p = PythonParser(file_name, content); p.parse()
                py_parsers[file_name] = p

                rel = p.get_python_relations()
                global_results["defined"].extend(rel["defined"])
                global_results["lambda_functions"].extend(rel["lambda_functions"])
                for func, calls in rel["called"].items():
                    global_results["called"].setdefault(func, []).extend(calls)
                global_results["comments"].extend(rel["comments"])
                file_results[file_name] = rel

            elif file_name.endswith(".js"):
                p = JsParser(file_name, content, project.files); p.parse()
                js_parsers[file_name] = p
                rel = p.get_js_relations()
                global_results["js"].setdefault("functions", []).extend(rel["defined"])
                global_results["js"].setdefault("comments", []).extend(rel["comments"])
                for func, calls in rel["called"].items():
                    global_results["js"].setdefault("called", {}).setdefault(func, []).extend(calls)
                file_results[file_name] = rel

            elif file_name.endswith(".c"):
                p = CParser(file_name, content, project.files); p.parse()
                c_parsers[file_name] = p
                rel = p.get_c_relations()
                global_results["comments"].extend(rel["comments"])
                global_results.setdefault("c", {}).setdefault("defined", []).extend(rel["defined"])
                for func, calls in rel["called"].items():
                    global_results.setdefault("c", {}).setdefault("called", {}).setdefault(func, []).extend(calls)
                file_results[file_name] = rel

            elif file_name.endswith(".html"):
                parser = HtmlParser(file_name, content, project.files); parser.parse([])
                global_results["html"].setdefault("tags", []).extend(parser.get_html_relations()["tags"])
                global_results["html"].setdefault("comments", []).extend(parser.get_html_relations()["comments"])
                file_results[file_name] = parser.get_html_relations()

            elif file_name.endswith(".css"):
                parser = CssParser(file_name, content, project.files); parser.parse()
                global_results["css"].setdefault("selectors", []).extend(parser.get_css_relations()["selectors"])
                global_results["css"].setdefault("comments", []).extend(parser.get_css_relations()["comments"])
                file_results[file_name] = parser.get_css_relations()

            else:
                file_results[file_name] = {"content": content}

        # pass 2 — build indices and edges (Python focus; cheap & robust)
        # map: function name -> list of definitions [{file, line, end_line}]
        def_index = {}
        for d in global_results["defined"]:
            def_index.setdefault(d["name"], []).append({"file": d.get("file"), "line": d.get("line"), "end_line": d.get("end_line")})

        # invert 'called' to 'called_by'
        for callee, calls in global_results["called"].items():
            for call in calls:
                global_results["called_by"].setdefault(callee, []).append(call)

        # edges from python calls with caller context
        for fname, parser in py_parsers.items():
            rel = parser.get_python_relations()
            for call in rel.get("calls", []):
                callee = call.get("callee")
                matches = def_index.get(callee, [])
                edge = {
                    "from": {"file": fname, "func": call.get("caller")},
                    "to": {"func": callee, "file": matches[0]["file"] if matches else None},
                    "line": call.get("line"),
                    "kind": call.get("kind"),
                }
                global_results["edges"].append(edge)

        # resolve imports to files (best-effort: module -> module.replace('.', '/')+'.py')
        def resolve_module(mod):
            if not mod: return None
            cand = mod.replace(".", "/") + ".py"
            return cand if cand in project.files else None

        for fname, parser in py_parsers.items():
            rel = parser.get_python_relations()
            resolved = []
            for imp in rel.get("imports", []):
                mod = imp["module"] or (imp["names"][0] if imp["names"] else None)
                resolved_file = resolve_module(mod)
                resolved.append({**imp, "resolved_file": resolved_file})
            global_results["imports_resolved"][fname] = resolved

        # simple per-file metrics
        for fname, content in project.files.items():
            words = len(re.findall(r"\b\w+\b", content))
            num_defs = sum(1 for d in global_results["defined"] if d.get("file") == fname)
            num_calls = 0
            if fname in py_parsers:
                num_calls += len(py_parsers[fname].get_python_relations().get("calls", []))
            if fname in js_parsers:
                num_calls += sum(len(v) for v in js_parsers[fname].get_js_relations().get("called", {}).values())
            if fname in c_parsers:
                num_calls += sum(len(v) for v in c_parsers[fname].get_c_relations().get("called", {}).values())
            global_results["metrics"][fname] = {"words": words, "num_functions": num_defs, "num_calls": num_calls}

        return global_results, file_results




    def get_project_tree(self, project_name):
        """Get the file structure (project tree) of a project."""
        project = self.projects.get(project_name)
        if not project:
            return "Project not found."
        return project.get_project_tree()

    def get_file_content(self, project_name, file_name):
        """Get the raw content of a specific file in the project."""
        project = self.projects.get(project_name)
        if not project:
            return "Project not found."
        return project.get_file_content(file_name)

    def get_parsed_functions(self, project_name, file_name):
        """Get the parsed functions (definitions and calls) for a specific file."""
        project = self.projects.get(project_name)
        if not project:
            return "Project not found."
        return project.get_parsed_functions(file_name)

    def get_function_calls_across_files(self, project_name, function_name):
        """Return a list of all files where the function is called, along with the line numbers."""
        project = self.projects.get(project_name)
        if not project:
            return "Project not found."
        
        function_calls = []
        global_results = self.global_results['called']
        if function_name in global_results:
            function_calls = global_results[function_name]
        
        return function_calls

    def delete_user(self, user_index):
        """Delete a user from the app."""
        try:
            user = self.users.pop(user_index)
            return f"User {user.name} deleted successfully."
        except IndexError:
            return "User not found."

class PrivateMessage(Message):
    def __init__(self, sender, receiver, content, timestamp=None):
        super().__init__(sender, content, timestamp)
        self.receiver = receiver

    def __repr__(self):
        return f"{self.timestamp} - {self.sender.name} to {self.receiver.name}: {self.content}"

class Conversation(Base):
    def __init__(self, user1, user2, title="Private Conversation"):
        super().__init__(user1.name, user1.email, user1.age)  # Using user1 details for the Base class
        self.user1 = user1
        self.user2 = user2
        self.title = title  # Set a title for the conversation (default is "Private Conversation")
        self.messages = []  # List of PrivateMessage objects
        self.participants = [user1, user2]  # Add participants to the conversation

    def add_message(self, sender, content):
        """Add a new message to the thread and notify participants."""
        new_message = Message(sender, content)
        self.messages.append(new_message)

        # Notify participants (except the sender) about the new message
        for participant in self.participants:
            if participant != sender:
                notification_message = f"New message in thread '{self.title}' by {sender.name}: {content}"
                participant.add_notification(notification_message)

    def get_conversation(self):
        """Return all messages in the conversation."""
        return self.messages

    def display_conversation(self):
        """Display the conversation by showing all the messages."""
        return "\n".join([repr(message) for message in self.messages])

    def like_message(self, message_index, user):
        """Like a message in the private conversation."""
        try:
            message = self.messages[message_index]
            return message.like(user)
        except IndexError:
            return "Message not found."

    def unlike_message(self, message_index, user):
        """Unlike a message in the private conversation."""
        try:
            message = self.messages[message_index]
            return message.unlike(user)
        except IndexError:
            return "Message not found."

class Project:
    def __init__(self, name, description, creator):
        self.name = name
        self.description = description
        self.creator = creator  # Store the creator
        self.files = {}  # Dictionary to hold files and their content
        self.functions = {}  # Dictionary to hold parsed functions (definitions and calls)
        self.participants = [creator]  # The creator is automatically a participant in the project
        self.liked_by = []  # List to store users who liked the project
        
    def add_file(self, file_name, content):
        self.files[file_name] = content

    def add_functions(self, file_name, function_data):
        self.functions[file_name] = function_data

    def get_project_tree(self):
        """Return the file names as the project tree."""
        return list(self.files.keys())

    def get_file_content(self, file_name):
        """Return the raw content of a file."""
        return self.files.get(file_name)

    def get_parsed_functions(self, file_name):
        """Return the parsed functions (definitions and calls) for a file."""
        return self.functions.get(file_name)

    def add_participant(self, user):
        """Add a user as a participant in the project and notify them."""
        if user not in self.participants:
            self.participants.append(user)
            self.send_notification(user, f"You've been added to the project '{self.name}' by {self.creator.name}.")
            self.creator.add_notification(f"{user.name} has been added to the project '{self.name}'.")
            return f"{user.name} has been added to the project."
        return f"{user.name} is already a participant."

    def send_notification(self, user, message):
        """Send notification to the user."""
        user.add_notification(message)

    def delete_project(self):
        """Delete the project and notify the creator."""
        message = f"The project '{self.name}' has been deleted."
        self.creator.add_notification(message)
        for participant in self.participants:
            if participant != self.creator:
                participant.add_notification(f"The project '{self.name}' has been deleted.")




class PythonParser:
    def __init__(self, file_name, file_content):
        self.file_name = file_name
        self.file_content = file_content
        print(f"Parsing file: {self.file_name}")  # Debugging line to check which file is being parsed
        print(f"File content: {self.file_content}")  # Debugging line to print the file content
        self.tree = ast.parse(file_content)
        self.function_definitions = []  # Track function definitions
        self.lambda_functions = []  # Track lambda functions (arrow functions)
        self.function_calls = {}  # Track function calls
        self.comments = []  # Track comments

    def parse(self):
        """Parse Python file for function definitions, lambda functions, function calls, and comments."""
        self._parse_function_definitions()  # Regular function definitions (def)
        self._parse_lambda_functions()  # Lambda functions
        self._parse_function_calls()  # Function calls
        self._parse_comments()  # Comments

    def _parse_function_definitions(self):
        """Detect declared function definitions in Python code."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef):  # Function defined with 'def'
                self.function_definitions.append({
                    'name': node.name,
                    'line': node.lineno
                })

    def _parse_lambda_functions(self):
        """Detect lambda (arrow) functions in Python code."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Lambda):  # Lambda functions in Python
                self.lambda_functions.append({
                    'name': 'lambda',  # Lambda functions are anonymous
                    'line': node.lineno  # Record the line number where the lambda is defined
                })

    def _parse_function_calls(self):
        """Detect function calls in Python code."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):  # Function call by name (e.g., test())
                    called_function = node.func.id
                    if called_function not in self.function_calls:
                        self.function_calls[called_function] = []
                    self.function_calls[called_function].append({
                        'file': self.file_name,
                        'line': node.lineno
                    })

    def _parse_comments(self):
        """Detect comments in Python files."""
        lines = self.file_content.splitlines()  # Split the content into lines
        for lineno, line in enumerate(lines, start=1):
            stripped_line = line.strip()
            if "#" in stripped_line:  # Match any line that contains '#'
                comment = stripped_line.split("#", 1)[1].strip()  # Extract comment after the '#'
                print(f"Detected comment: {comment} on line {lineno}")  # Debugging line to verify detection

                self.comments.append({
                    'line': lineno,  # The actual line number in the file
                    'comment': comment  # Comment text
                })



    def get_python_relations(self):
        """Return Python function definitions, lambda functions, function calls, and comments."""
        return {
            'defined': self.function_definitions,  # Return declared functions (def)
            'lambda_functions': self.lambda_functions,  # Return lambda (arrow) functions
            'called': self.function_calls,  # Return function calls
            'comments': self.comments  # Return comments
        }

class CParser:
    def __init__(self, file_name, file_content, all_files):
        self.file_name = file_name
        self.file_content = file_content
        self.all_files = all_files
        self.function_definitions = []
        self.function_calls = {}
        self.function_pointers = []  # Track function pointer calls
        self.comments = []

    def parse(self):
        """Parse C file for function definitions, calls, pointers, and comments."""
        self._parse_function_definitions()
        self._parse_function_calls()
        self._parse_function_pointers()  # Detect pointer-based function calls
        self._parse_comments()

    def _parse_function_definitions(self):
        """Detect function definitions in C files."""
        function_defs = re.findall(r"\w+\s+\w+\s*\([^)]*\)\s*{", self.file_content)
        for func in function_defs:
            func_name = func.split('(')[0].split()[-1]
            self.function_definitions.append({'name': func_name})

    def _parse_function_calls(self):
        """Detect function calls in C files."""
        function_calls = re.findall(r"(\w+)\s*\(", self.file_content)
        for call in function_calls:
            if call not in self.function_calls:
                self.function_calls[call] = []
            self.function_calls[call].append({
                'file': self.file_name,
            })

    def _parse_function_pointers(self):
        """Detect function pointer assignments and calls in C files."""
        # Detect function pointer assignment (e.g., void (*func_ptr)() = test;)
        pointer_assignments = re.findall(r"\s*\(\*\s*(\w+)\s*\)\s*\(\)\s*=\s*(\w+)\s*;", self.file_content)
        for ptr, func in pointer_assignments:
            self.function_pointers.append({
                'pointer': ptr,
                'function': func,
                'file': self.file_name,
            })

        # Detect calls using function pointers (e.g., func_ptr();)
        pointer_calls = re.findall(r"(\w+)\s*\(\)\s*;", self.file_content)
        for ptr in pointer_calls:
            self.function_pointers.append({
                'pointer': ptr,
                'file': self.file_name,
            })

    def _parse_comments(self):
        """Detect comments in C files."""
        single_line_comments = re.findall(r"//(.*)", self.file_content)
        for i, comment in enumerate(single_line_comments, start=1):
            self.comments.append({
                'line': i,
                'comment': comment.strip()
            })

        multi_line_comments = re.findall(r"/\*.*?\*/", self.file_content, re.DOTALL)
        for i, comment in enumerate(multi_line_comments, start=1):
            self.comments.append({
                'line': i,
                'comment': comment.strip()
            })

    def get_c_relations(self):
        """Return C function definitions, calls, pointers, and comments."""
        return {
            'defined': self.function_definitions,
            'called': self.function_calls,
            'function_pointers': self.function_pointers,  # Return function pointer calls
            'comments': self.comments
        }

class CssParser:
    def __init__(self, file_name, file_content, all_files):
        self.file_name = file_name  # Store the CSS file name
        self.file_content = file_content
        self.all_files = all_files  # Dictionary of all files in the project (for cross-file call tracking)
        self.selectors = []  # List to store CSS selectors and their properties
        self.comments = []  # List to store comments (with line and text)
        self.class_selectors = []  # List to store class selectors (e.g., .container)
        self.id_selectors = []  # List to store ID selectors (e.g., #header)
        self.matched_html = {}  # Dictionary to store HTML tags that are styled by this CSS

    def parse(self):
        """Parse CSS file for selectors, properties, and comments."""
        self._parse_selectors()
        self._parse_comments()

    def _parse_selectors(self):
        """Detect CSS selectors (class, id) and their properties."""
        # Regular expression to match selectors and their properties
        selector_pattern = r'([a-zA-Z0-9\s\.\#\-\:]+)\s*\{(.*?)\}'
        matches = re.findall(selector_pattern, self.file_content, re.DOTALL)
        
        for selector, properties in matches:
            properties_dict = self._parse_properties(properties)  # Parse the properties of the selector
            self.selectors.append({
                'selector': selector.strip(),
                'properties': properties_dict
            })

            # Track class selectors (e.g., .container)
            if selector.startswith('.'):
                self.class_selectors.append(selector.strip())

            # Track ID selectors (e.g., #header)
            if selector.startswith('#'):
                self.id_selectors.append(selector.strip())

    def _parse_properties(self, properties_string):
        """Parse the CSS properties and values."""
        properties = {}
        # Regular expression to match property-value pairs
        property_pattern = r'([a-zA-Z\-]+)\s*:\s*([^;]+);'
        matches = re.findall(property_pattern, properties_string)
        
        for prop, value in matches:
            properties[prop.strip()] = value.strip()
        return properties

    def _parse_comments(self):
        """Detect comments in CSS files."""
        # Match comments: /* comment */
        comment_pattern = r'/\*(.*?)\*/'
        comments = re.findall(comment_pattern, self.file_content, re.DOTALL)
        
        for i, comment in enumerate(comments, start=1):
            self.comments.append({
                'line': i,
                'comment': comment.strip()
            })

    def match_html_tags(self, html_parsers):
        """Match CSS selectors with HTML tags in HTML files."""
        for html_parser in html_parsers:
            # Match class selectors in HTML
            for selector in self.class_selectors:
                for tag in html_parser.tags:
                    if 'class' in tag['attributes'] and tag['attributes']['class'] == selector[1:]:
                        if selector not in self.matched_html:
                            self.matched_html[selector] = []
                        self.matched_html[selector].append({
                            'html_file': html_parser.file_name,
                            'tag': tag['tag'],
                            'attributes': tag['attributes']
                        })

            # Match ID selectors in HTML
            for selector in self.id_selectors:
                for tag in html_parser.tags:
                    if 'id' in tag['attributes'] and tag['attributes']['id'] == selector[1:]:
                        if selector not in self.matched_html:
                            self.matched_html[selector] = []
                        self.matched_html[selector].append({
                            'html_file': html_parser.file_name,
                            'tag': tag['tag'],
                            'attributes': tag['attributes']
                        })

    def get_css_relations(self):
        """Return detected CSS selectors, properties, comments, and matched HTML tags."""
        return {
            'selectors': self.selectors,  # List of CSS selectors and their properties
            'class_selectors': self.class_selectors,  # List of class selectors (e.g., .container)
            'id_selectors': self.id_selectors,  # List of ID selectors (e.g., #header)
            'comments': self.comments,  # List of comments (line and text)
            'matched_html': self.matched_html  # Matched HTML tags (with class/id attributes)
        }

class HtmlParser:
    def __init__(self, file_name, file_content, all_files):
        self.file_name = file_name  # Store the file name
        self.file_content = file_content
        self.all_files = all_files  # Dictionary of all files in the project (for cross-file call tracking)
        self.tags = []  # List to store HTML tags and their attributes
        self.comments = []  # List to store comments (with line and text)
        self.scripts = []  # List to store embedded JavaScript code
        self.styles = []  # List to store embedded CSS code
        self.matched_css = {}  # Dictionary to store CSS files where each class/id is used

    def parse(self, css_parsers):
        """Parse HTML file for tags, embedded JavaScript, comments, and match CSS styles."""
        self._parse_tags()
        self._parse_comments()
        self._parse_scripts()
        self._parse_styles()
        self._match_css(css_parsers)

    def _parse_tags(self):
        """Detect HTML tags and their attributes in the file."""
        tag_pattern = r'<([a-zA-Z0-9\-]+)([^>]*)>'
        matches = re.findall(tag_pattern, self.file_content)
        for tag, attributes in matches:
            # Capture the tag and attributes
            self.tags.append({
                'tag': tag,
                'attributes': self._parse_attributes(attributes)
            })

    def _parse_attributes(self, attributes_string):
        """Extract attributes from an HTML tag."""
        attributes = {}
        attribute_pattern = r'([a-zA-Z\-]+)=\"([^\"]*)\"'
        matches = re.findall(attribute_pattern, attributes_string)
        for attr_name, attr_value in matches:
            attributes[attr_name] = attr_value
        return attributes

    def _parse_comments(self):
        """Detect comments in HTML files."""
        comment_pattern = r'<!--(.*?)-->'
        comments = re.findall(comment_pattern, self.file_content, re.DOTALL)
        for comment in comments:
            self.comments.append({
                'comment': comment.strip()
            })

    def _parse_scripts(self):
        """Extract JavaScript embedded within <script> tags."""
        script_pattern = r'<script.*?>(.*?)</script>'
        scripts = re.findall(script_pattern, self.file_content, re.DOTALL)
        self.scripts.extend(scripts)

    def _parse_styles(self):
        """Extract CSS embedded within <style> tags."""
        style_pattern = r'<style.*?>(.*?)</style>'
        styles = re.findall(style_pattern, self.file_content, re.DOTALL)
        self.styles.extend(styles)

    def _match_css(self, css_parsers):
        """Match HTML elements (class/id) with selectors in CSS files."""
        for css_parser in css_parsers:
            for selector in css_parser.get_css_relations()['class_selectors']:
                # Match class selectors in HTML tags
                for tag in self.tags:
                    if 'class' in tag['attributes'] and tag['attributes']['class'] == selector[1:]:
                        if selector not in self.matched_css:
                            self.matched_css[selector] = []
                        self.matched_css[selector].append({
                            'file': self.file_name,
                            'tag': tag['tag'],
                            'attributes': tag['attributes']
                        })

            for selector in css_parser.get_css_relations()['id_selectors']:
                # Match id selectors in HTML tags
                for tag in self.tags:
                    if 'id' in tag['attributes'] and tag['attributes']['id'] == selector[1:]:
                        if selector not in self.matched_css:
                            self.matched_css[selector] = []
                        self.matched_css[selector].append({
                            'file': self.file_name,
                            'tag': tag['tag'],
                            'attributes': tag['attributes']
                        })

    def get_html_relations(self):
        """Return parsed HTML tags, comments, scripts, styles, and matched CSS files."""
        return {
            'tags': self.tags,  # List of HTML tags and their attributes
            'comments': self.comments,  # List of comments (line and text)
            'scripts': self.scripts,  # Embedded JavaScript
            'styles': self.styles,  # Embedded CSS
            'matched_css': self.matched_css  # Matched CSS selectors
        }

class JsParser:
    def __init__(self, file_name, file_content, all_files):
        self.file_name = file_name
        self.file_content = file_content
        self.all_files = all_files
        self.function_definitions = []  # To store function definitions
        self.function_calls = {}  # To store function calls
        self.arrow_functions = []  # Track arrow functions
        self.comments = []

    def parse(self):
        """Parse the JavaScript file for function definitions, arrow functions, calls, and comments."""
        self._parse_function_definitions()
        self._parse_arrow_functions()
        self._parse_function_calls()
        self._parse_comments()

    def _parse_function_definitions(self):
        """Detect regular function definitions in JavaScript files."""
        function_defs = re.findall(r"function\s+(\w+)\s*\(", self.file_content)
        for func in function_defs:
            self.function_definitions.append({'name': func})

    def _parse_arrow_functions(self):
        """Detect arrow function definitions in JavaScript files."""
        # Check for arrow function syntax: const test = () => { ... }
        arrow_function_pattern = r"(\w+)\s*=\s*\(\s*[^)]*\)\s*=>"
        matches = re.findall(arrow_function_pattern, self.file_content)
        for func in matches:
            self.arrow_functions.append({'name': func})

    def _parse_function_calls(self):
        """Detect function calls in JavaScript files."""
        function_calls = re.findall(r"(\w+)\s*\(", self.file_content)
        for call in function_calls:
            if call not in self.function_calls:
                self.function_calls[call] = []
            self.function_calls[call].append({
                'file': self.file_name,
            })

    def _parse_comments(self):
        """Detect comments in JavaScript files."""
        single_line_comments = re.findall(r"//(.*)", self.file_content)
        for i, comment in enumerate(single_line_comments, start=1):
            self.comments.append({
                'line': i,
                'comment': comment.strip()
            })

        multi_line_comments = re.findall(r"/\*.*?\*/", self.file_content, re.DOTALL)
        for i, comment in enumerate(multi_line_comments, start=1):
            self.comments.append({
                'line': i,
                'comment': comment.strip()
            })

    def get_js_relations(self):
        """Return JavaScript function definitions, arrow functions, calls, and comments."""
        return {
            'defined': self.function_definitions,
            'arrow_functions': self.arrow_functions,  # Only arrow functions detected this way
            'called': self.function_calls,
            'comments': self.comments
        }

