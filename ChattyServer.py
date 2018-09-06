# server for the ChattY chat
# made by Yedaya Katsman 26/07/2018
import socket, select, errno
import json
import sqlite3
import sys
import smtplib
from random import randint


class SQL:
    def __init__(self):
        self.Connection = sqlite3.connect('ChattyQuery.db')
        self.cursor = self.Connection.cursor()
        try:
            self.cursor.execute('''CREATE TABLE users
                                   (username TEXT PRIMARY KEY, email TEXT, firstName TEXT,
                                    lastName TEXT, birthDate TEXT, password TEXT, image INTEGER, code INTEGER)''')
        except Exception as error:
            print error, "line: %d" % sys.exc_info()[-1].tb_lineno
            pass

    def InsertNewUser(self, regInfo):
        print "inserting new user..."
        self.cursor.execute('''INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', regInfo)
        self.Connection.commit()

    def Select(self, command, args):
        self.cursor.execute(command, args)
        results = self.cursor.fetchall()
        if results:
            return results[0][0]

    def Update(self, command, args):
        self.cursor.execute(command, args)


class Server(object):
    def __init__(self):
        self.running = True

        self.Rooms = [[], [], [], []]

        self.DataBase = SQL()
        try:
            self.serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.serverSocket.bind(('0.0.0.0', 35628))
            self.serverSocket.listen(50)
            print "connected"
        except Exception as error:
            # print error, "line: %d" % sys.exc_info()[-1].tb_lineno
            print "couldn't connect"

    def loop(self):
        self.ConnectedClients = {}  # list of dictionaries that containes usernames and their respective socket objects
        self.MessagesToSend = []
        self.CloseList = []
        try:
            while self.running:
                rlist, wlist, xlist = select.select(
                    [self.serverSocket] + [user.socket for user in Users.UsersList],
                    [user.socket for user in Users.UsersList], []
                )
                if rlist:
                    for CurrentSocket in rlist:
                        if CurrentSocket is self.serverSocket:
                            (newSocket, address) = self.serverSocket.accept()
                            a = Users(newSocket)
                        else:
                            try:
                                receivedMessage = CurrentSocket.recv(8192)
                            except Exception as error:
                                # deleting socket from dictionary by finding index of it and finding key which corresponds to it
                                Users.RemoveBySocket(CurrentSocket)
                                break
                            if receivedMessage == "":
                                Users.RemoveBySocket(CurrentSocket)
                                CurrentSocket.close()
                            else:
                                self.ProcessMessage(receivedMessage, Users.GetBySocket(CurrentSocket))
                if wlist and self.MessagesToSend:
                    for message in self.MessagesToSend:
                        if not message[1] in self.ConnectedClients.iterkeys():
                            self.MessagesToSend.remove(message)
                        elif self.ConnectedClients[
                            message[1]] in wlist:  # checking if any of the messages are for user who can accept them
                            encodedMsg = json.dumps(message[0],
                                                    separators=(',', ':'))  # encoding dictionary to text for delivery
                            try:
                                self.ConnectedClients[message[1]].send(encodedMsg)
                                print "sending message %s to %s" % (encodedMsg, message[1])
                            except socket.error:
                                del self.ConnectedClients[message[1]]
                            self.MessagesToSend.remove((message))
                if self.CloseList:
                    for client in self.CloseList:
                        self.ConnectedClients[client].close()
                        del self.ConnectedClients[client]
                        self.CloseList.remove(client)
        except Exception as error:
            pass
        # print error, " line: %d" % sys.exc_info()[-1].tb_lineno
        finally:
            print "server closed"
            self.serverSocket.close()

    def ProcessMessage(self, message, sender):
        message = json.loads(message)

        self.doubleLogin = False

        if not sender.username:
            if not sender.SetName(message['username']):
                self.doubleLogin = True



        # for username, socket in self.ConnectedClients.iteritems():
        #     if socket == sender:  # finding the username of the sender socket
        #         if username == "":
        #             sender = message['username']
        #             if sender in self.ConnectedClients:
        #                 self.doubleLogin = True
        #             self.ConnectedClients[sender] = socket
        #             del self.ConnectedClients[username]
        #             break
        #         else:
        #             sender = username

        action = message["opcode"]  # getting action requested by clien
        if action == "register":
            try:
                self.DataBase.InsertNewUser((message['username'], message['email'],
                                             message['firstName'], message['lastName'],
                                             message['birthDate'], message['password'],
                                             message['image'], 0,))
                self.MessagesToSend.append(({'opcode': 'regConfirm', 'success': 1, 'error': ""}, sender))
            except Exception as error:
                print error
                self.MessagesToSend.append((
                    {'opcode': 'regConfirm', 'success': 0, 'error': "username already exists in system"}, sender))
                self.ConnectedClients[""] = self.ConnectedClients[sender]
                del self.ConnectedClients[sender]

        if action == 'login':
            # checking if password matches the database
            hash = self.DataBase.Select(
                '''SELECT password FROM users WHERE username=?''', (message['username'],))
            if not hash or hash != message['password']:
                self.MessagesToSend.append((
                    {'opcode': 'loginConfirm', 'success': 0, 'error': 'Username or password are incorrect'}
                    , sender))
                self.ConnectedClients[""] = self.ConnectedClients[sender]
                del self.ConnectedClients[sender]
            elif hash == message['password']:
                if not self.doubleLogin:
                    self.MessagesToSend.append(({'opcode': 'loginConfirm', 'success': 1, 'error': ''}, sender))
                else:
                    print "double login"
                    self.MessagesToSend.append(({'opcode': 'loginConfirm', 'success': 0,
                                                 'error': 'You are already logged in on another device'},
                                                sender))
        if action == 'logout':
            self.CloseList.append(sender)
            del self.ConnectedClients[sender]

        if action == 'joinRoom':
            if message['roomID'] <= 3 and message['roomID'] >= 0:
                self.Rooms[message['roomID']].append(sender)
                self.MessagesToSend.append((
                    {'opcode': 'roomConfirm', 'success': 1, 'error': ""}
                    , sender))
            else:
                self.MessagesToSend.append(
                    ({'opcode': 'roomConfirm', 'success': 0, 'error': "room does not exist"}, sender))

        if action == 'message':
            print "Rooms: %s" % self.Rooms
            for client in self.Rooms[message['room']]:
                self.MessagesToSend.append(
                    ({'opcode': 'messageToYou', 'message': message['message'], 'sender': sender}, client))

        if action == 'forgotPassword':
            code = randint(100000, 999999)
            email = self.DataBase.Select('''SELECT email FROM users WHERE username = ?''', (message['username'],))
            if email == message['email']:
                gmail_user = 'serverchatty@gmail.com'
                gmail_password = 'super secret'

                sent_from = gmail_user
                to = [email]
                subject = 'Chatty Password reset'
                body = "your one time code is %s" % code

                email_text = """\  
                From: %s  
                To: %s  
                Subject: %s
    
                %s
                """ % (sent_from, ", ".join(to), subject, body)

                try:
                    server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
                    server.ehlo()
                    server.login(gmail_user, gmail_password)
                    server.sendmail(sent_from, to, email_text)
                    server.close()

                    print 'Email sent!'
                    self.MessagesToSend.append(({'opcode': 'codeConfirm', 'success': 1, 'error': ''}, sender))
                except:
                    print 'Something went wrong...'
                    self.MessagesToSend.append(
                        ({'opcode': 'codeConfirm', 'success': 0, 'error': 'email doesn\'t exist'}, sender))
        if action == 'resetPassword':
            self.DataBase.Update('''UPDATE users SET password = ? WHERE username = ?''',
                                 (message['newPassword'], sender))
            self.MessagesToSend.append(({'opcode': 'resetConfirm', 'success': 1}, sender))


class Users(object):
    UsersList = []

    @staticmethod
    def GetByName(username):
        for user in Users.UsersList:
            if user.username == username:
                return user
        return None

    @staticmethod
    def GetBySocket(socket):
        for user in Users.UsersList:
            if user.socket == socket:
                return user
        return None

    @staticmethod
    def GetByID(id):
        for user in Users.UsersList:
            if user.id == id:
                return user
        return None

    @staticmethod
    def RemoveByID(id):
        for user in Users.UsersList:
            if user.id == id:
                Users.UsersList.remove(user)

    @staticmethod
    def RemoveByName(username):
        for user in Users.UsersList:
            if user.username == username:
                Users.UsersList.remove(user)

    @staticmethod
    def RemoveBySocket(socket):
        for user in Users.UsersList:
            if user.socket is socket:
                Users.UsersList.remove(user)

    def __init__(self, socket, username=''):
        self.socket = socket
        self.username = username
        self.id = len(type(self).UsersList) + 1
        type(self).UsersList.append(self)

    def SetName(self, username):
        if type(self).GetByName(username):
            return False
        self.username = username
        return True



def main():
    server = Server()
    server.loop()


if __name__ == "__main__":
    main()
