#!/usr/bin/python
# Copyright (c) 2021 Arista Networks, Inc.
# Use of this source code is governed by the Apache License 2.0
# that can be found in the COPYING file.

import subprocess
import requests
import os
import json
import sys
from SysdbHelperUtils import SysdbPathHelper
import Cell
import urlparse


############## USER INPUT #############
cvAddr = "www.arista.io"
enrollmentToken = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRhc2V0SUQiOjcyMzEyODYwODY2NTAwNDkzMDIsImV4cCI6MTY5NDEyMjk1OSwia2lkIjoiOGJhYzZjYTRhZDk1Y2U0NiIsIm5iZiI6MTY5MTUzMDk1OSwicmVlbnJvbGxEZXZpY2VzIjpbIioiXX0.ke9PSAWdiU9lCbSVXU_oBJW_gBdiExLtOVVx6RkvyGbkpqK-YZdmrkTdCWDM9PzzfcGYOVV_keICS3ZaXZGzq0ZaYkmCJyTgVPRZcdh7Gb9_P9aixVuhP_hJVPYpBkzEbpzUPfeDa0sJsyJxWfqN5TXyFRA_sX4yUrPcNoJpVUaqWmwWPKO55JEs7KpNmmnJFy0Nv1YXLDUMd057STuisiZMDtZNZS01-Xq86Dlm_VEJYlKqgEbaWQrBHQ_C_Vm_Unwt3ZFMBRyM9-HVhNsmFJdnX-nNTbAol0MJW7CyrndyQAxxXw8lEEZIybhieoTNz38pWnmGNmFWlygsJ_nh0V-Oj2JO5SzGKQq124odOy9gQc7rydqWw_ZIMhHWgaUsrBxkF4OaJC16CMgcMeP6BpdplVX22Yvmpsj9Y6hAUxBRgRyaNgrumWvepCR6RSYBsC5rXH01cqh4xtsciRWNoA2_piHzzew00NBZGi_aaZALRYxRXnF96qKIVqKrxhBYe29fB6qSCq9P_cCygfL4K8sjDHAz0ZxH8tSrdllV0SiX-rEkxrIT1SAt9uoCJev55EqQHs4qbHYzrxRxVc8VuPtc_YBErcp3oRr-eHdoQp4GaO_itq4rE0VdH9OCjCPv2deipbT5QXAHRhQawiGBsI5gKNAnYPslQ2Y2RVj6UbE"


############## CONSTANTS ##############
SECURE_HTTPS_PORT = "443"
SECURE_TOKEN = "token-secure"
INGEST_PORT = "9910"
INGEST_TOKEN = "token"
TOKEN_FILE_PATH = "/tmp/token.tok"
BOOT_SCRIPT_PATH = "/tmp/bootstrap-script"


########### HELPER FUNCTIONS ##########
# Given a filepath and a key, getValueFromFile searches for key=VALUE in it
# and returns the found value without any whitespaces. In case no key specified,
# gives the first string in the first line of the file.
def getValueFromFile( filename, key ):
   if not key:
      with open( filename, "r" ) as f:
         return f.readline().split()[ 0 ]
   else:
      with open( filename, "r" ) as f:
         lines = f.readlines()
         for line in lines:
            if key in line :
               return line.split( "=" )[ 1 ].rstrip( "\n" )
   return None


########### MAIN SCRIPT ##########
class BootstrapManager( object ):
   def __init__( self ):
      super( BootstrapManager, self ).__init__()

##################################################################################
# step 1: get client certificate using the enrollment token
##################################################################################
   def getClientCerficates( self ):
      with open( TOKEN_FILE_PATH, "w" ) as f:
         f.write( enrollmentToken )

      cmd = "/usr/bin/TerminAttr"
      cmd += " -cvauth " + self.tokenType + "," + TOKEN_FILE_PATH
      cmd += " -cvaddr " + self.enrollAddr
      cmd += " -enrollonly"

      try:
         subprocess.check_output( cmd, shell=True, stderr=subprocess.STDOUT )
      except subprocess.CalledProcessError as e:
         print( e.output )
         raise e
      print( "step 1 done, exchanged enrollment token for client certificates" )

##################################################################################
# Step 2: get the path of stored client certificate
##################################################################################

   def getCertificatePaths( self ):
      cmd = "/usr/bin/TerminAttr"
      cmd += " -cvaddr " + self.enrollAddr
      cmd += " -certsconfig"

      try:
         response = subprocess.check_output( cmd,
               shell=True, stderr=subprocess.STDOUT )
         json_response = json.loads( response )
         self.certificate = str( json_response[ self.enrollAddr ][ 'certFile' ] )
         self.key = str( json_response[ self.enrollAddr ][ 'keyFile' ] )
      except subprocess.CalledProcessError:
         basePath = "/persist/secure/ssl/terminattr/primary/"
         self.certificate = basePath + "certs/client.crt"
         self.key = basePath + "keys/client.key"

      print( "step 2 done, obtained client certificates location from TA" )
      print( "ceriticate location: " + self.certificate )
      print( "key location: " + self.key )

##################################################################################
# step 3 get bootstrap script using the certificates
##################################################################################

   def getBootstrapScript( self ):
      # setting Sysdb access variables
      sysname = os.environ.get( "SYSNAME", "ar" )
      pathHelper = SysdbPathHelper( sysname )

      # sysdb paths accessed
      cellID = str( Cell.cellId() )
      mibStatus = pathHelper.getEntity( "hardware/entmib" )
      tpmStatus = pathHelper.getEntity( "cell/" + cellID + "/hardware/tpm/status" )
      tpmConfig = pathHelper.getEntity( "cell/" + cellID + "/hardware/tpm/config" )

      # setting header information
      headers = {}
      headers[ 'X-Arista-SystemMAC' ] = mibStatus.systemMacAddr
      headers[ 'X-Arista-ModelName' ] = mibStatus.root.modelName
      headers[ 'X-Arista-HardwareVersion' ] = mibStatus.root.hardwareRev
      headers[ 'X-Arista-Serial' ] = mibStatus.root.serialNum

      headers[ 'X-Arista-TpmApi' ] = tpmStatus.tpmVersion
      headers[ 'X-Arista-TpmFwVersion' ] = tpmStatus.firmwareVersion
      headers[ 'X-Arista-SecureZtp' ] = str( tpmConfig.antiCounterfeitingSupported )

      headers[ 'X-Arista-SoftwareVersion' ] = getValueFromFile(
            "/etc/swi-version", "SWI_VERSION" )
      headers[ 'X-Arista-Architecture' ] = getValueFromFile( "/etc/arch", "" )

      # making the request and writing to file
      response = requests.get( self.bootScriptAddr, headers=headers,
        cert=( self.certificate, self.key ) )
      response.raise_for_status()
      with open( BOOT_SCRIPT_PATH, "w" ) as f:
         f.write( response.text )

      print( "step 3.1 done, bootstrap script fetched and stored on disk" )

   # execute the obtained bootstrap file
   def executeBootstrap( self ):
      cmd = "python " + BOOT_SCRIPT_PATH
      try:
         subprocess.check_output( cmd, shell=True, stderr=subprocess.STDOUT )
      except subprocess.CalledProcessError as e:
         print( e.output )
         raise e
      print( "step 3.2 done, executing the fetched bootstrap script" )

   def run( self ):
      self.getClientCerficates()
      self.getCertificatePaths()
      self.getBootstrapScript()
      self.executeBootstrap()


class CloudBootstrapManager( BootstrapManager ):
   def __init__( self ):
      super( CloudBootstrapManager, self ).__init__()

      cvAddrURL = urlparse.urlparse( cvAddr )
      if cvAddrURL.netloc == "":
         cvAddrURL = cvAddrURL._replace( path="", netloc=cvAddrURL.path )
      if cvAddrURL.path == "":
         cvAddrURL = cvAddrURL._replace( path="/ztp/bootstrap" )
      if cvAddrURL.scheme == "":
         cvAddrURL = cvAddrURL._replace( scheme="https" )

      self.tokenType = SECURE_TOKEN
      self.enrollAddr = cvAddrURL.netloc + ":" + SECURE_HTTPS_PORT
      self.enrollAddr = self.enrollAddr.replace( "www", "apiserver" )
      self.bootScriptAddr = cvAddrURL.geturl()


class OnPremBootstrapManager( BootstrapManager ):
   def __init__( self ):
      super( OnPremBootstrapManager, self ).__init__()

      cvAddrURL = urlparse.urlparse( cvAddr )
      if cvAddrURL.netloc == "":
         cvAddrURL = cvAddrURL._replace( path="", netloc=cvAddrURL.path )
      if cvAddrURL.path == "":
         cvAddrURL = cvAddrURL._replace( path="/ztp/bootstrap" )
      if cvAddrURL.scheme == "":
         cvAddrURL = cvAddrURL._replace( scheme="http" )

      self.tokenType = INGEST_TOKEN
      self.enrollAddr = cvAddrURL.netloc + ":" + INGEST_PORT
      self.bootScriptAddr = cvAddrURL.geturl()


if __name__ == "__main__":
   # check inputs
   if cvAddr == "":
      sys.exit( "error: address to CVP missing" )
   if enrollmentToken == "":
      sys.exit( "error: enrollment token missing" )

   # check whether it is cloud or on prem
   if cvAddr.find( "arista.io" ) != -1 :
      bm = CloudBootstrapManager()
   else:
      bm = OnPremBootstrapManager()

   # run the script
   bm.run()
