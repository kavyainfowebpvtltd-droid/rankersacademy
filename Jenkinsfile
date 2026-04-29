pipeline {
 agent any

 stages {

   stage('Checkout Code') {
      steps {
         git branch: 'main',
         url: 'https://github.com/kavyainfowebpvtltd-droid/rankersacademy.git'
      }
   }

   stage('Docker Build') {
      steps {
         sh '''
         docker compose -p rankersacademy build web
         '''
      }
   }

   stage('Docker Deploy') {
      steps {
         sh '''
         docker compose -p rankersacademy up -d --no-deps --force-recreate web
         docker image prune -f
         '''
      }
   }

   stage('Verify Container') {
      steps {
         sh '''
         sleep 20
         docker ps | grep rankers-app
         '''
      }
   }

 }

 post {

   success {
      echo 'SUCCESS Deployment Completed'
   }

   failure {
      echo 'FAILED Deployment Failed'
   }

   always {
      sh 'docker ps'
   }

 }
}
