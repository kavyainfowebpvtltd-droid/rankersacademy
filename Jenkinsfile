pipeline {
    agent any

    stages {

        stage('Checkout') {
            steps {
                git branch: 'main',
                url: 'https://github.com/kavyainfowebpvtltd-droid/rankersacademy.git'
            }
        }

        stage('Build Image') {
            steps {
                sh '''
                docker compose -p rankersacademy build web
                '''
            }
        }

        stage('Deploy') {
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
                sleep 15
                curl -f https://rankersonlinetest.com
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
            sh 'docker ps'
        }
    }
}
