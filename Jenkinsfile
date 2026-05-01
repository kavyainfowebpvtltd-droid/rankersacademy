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

         echo "Waiting for container..."
         sleep 15

         echo "Running migrations..."
         docker exec rankers-app python manage.py migrate

         echo "Collecting static files..."
         docker exec rankers-app python manage.py collectstatic --noinput

         docker image prune -f
         '''
      }
   }

   stage('Verify Container') {
      steps {
         sh '''
         sleep 10
         docker ps | grep rankers-app
         '''
      }
   }

 }

 post {

   success {
      echo 'Deployment + Migration Successful'
   }

   failure {
      echo 'Deployment Failed'
   }

   always {
      sh 'docker ps'
   }

 }
}
