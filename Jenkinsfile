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
                docker --version
                docker compose version
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
                echo "Waiting for application startup..."

                for i in {1..10}
                do
                  if curl -f http://127.0.0.1:8081 > /dev/null 2>&1
                  then
                     echo "Application Healthy"
                     exit 0
                  fi

                  echo "Retry $i/10 ..."
                  sleep 10
                done

                echo "Health Check Failed"
                exit 1
                '''
            }
        }
    }

    post {

        success {
            echo 'Deployment Successful'
        }

        failure {
            echo 'Deployment Failed'
        }

        always {
            sh '''
            echo "Running Containers:"
            docker ps
            '''
        }
    }
}
