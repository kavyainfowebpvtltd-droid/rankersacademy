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

  stage('Health Check') {
   steps {
    sh '''
    echo "Waiting for app startup..."
    sleep 30

    count=1
    while [ $count -le 10 ]
    do
      if curl -f http://127.0.0.1:8081 >/dev/null 2>&1
      then
         echo "App healthy"
         exit 0
      fi

      echo "Retry $count/10"
      sleep 10
      count=$((count+1))
    done

    echo "Health check failed"
    exit 1
    '''
   }
  }

 }

 post {
   success {
      echo 'SUCCESS Deploy Completed'
   }

   failure {
      echo 'FAILED Deploy Failed'
   }

   always {
      sh 'docker ps'
   }
 }
}
